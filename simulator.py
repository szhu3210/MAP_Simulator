import configuration
import random
import math
import collections
import time
import os
import sys

import logging
logging.basicConfig(datefmt='%m/%d/%Y %H:%M:%S', level=logging.WARNING)

# rootLogger = logging.getLogger()
#
# logFormatter = logging.Formatter("%(asctime)s  %(message)s")
# logFormatter = logging.Formatter("%(message)s")
# fileHandler = logging.FileHandler('logs/simulator.log')
# fileHandler.setFormatter(logFormatter)
# rootLogger.addHandler(fileHandler)
#
# logFormatter = logging.Formatter("%(message)s")
# consoleHandler = logging.StreamHandler()
# consoleHandler.setFormatter(logFormatter)
# rootLogger.addHandler(consoleHandler)


class Tx(object):

    def __init__(self, l, name, dest, csEnabled=False, hidden=[]):
        self.name = name
        self.backoffTimeMax = configuration.CW0 - 1
        self.l = l
        self.nextTrafficTime = self.generate_traffic_interval()
        self.nextTrafficSlot = math.ceil(self.nextTrafficTime / configuration.slotDuration + 1)
        self.job = collections.deque()
        self.message = collections.deque()
        self.slotIndex = 0
        self.packetNumber = 0
        self.packetNumberSuccess = 0
        self.destination = dest
        self.csEnabled = csEnabled
        self.ackBuffer = 0
        self.ctsBuffer = 0
        self.hidden = hidden
        self.collisionCounter = 0

    def sending(self):
        return self.job and 'send' in self.job[0]

    def generate_traffic_interval(self):
        return -(1.0/self.l)*math.log(random.random()) * (10 ** 6)

    def CSMA_pattern_pre(self):
        res = []
        res.extend(['DIFS'] * configuration.DIFSSlotSize)
        res.extend(['backoff %d' % i for i in range(random.randint(0, self.backoffTimeMax), 0, -1)])
        if self.csEnabled:
            res.extend(['send RTS %d -> %s' % (i, self.destination) for i in range(1, configuration.rtsFrameSlotSize+1)])
            res.extend(['SIFS'] * configuration.SIFSSlotSize)
            res.extend(['CTS %d' % i for i in range(1, configuration.ctsFrameSlotSize+1)])
            res.extend(['SIFS'] * configuration.SIFSSlotSize)
        return res

    def CSMA_pattern(self):
        res = self.CSMA_pattern_pre()
        res.extend(['send data %s -> %s %d' % (self.name, self.destination, i) for i in range(1, configuration.dataFrameSlotSize+1)])
        res.extend(['SIFS'] * configuration.SIFSSlotSize)
        res.extend(['ACK 1', 'ACK 2'])
        return res

    def resetDIFS(self):
        while self.job and self.job[0]=='DIFS':
            self.job.popleft()
        self.job.extendleft(['DIFS'] * configuration.DIFSSlotSize)
        logging.info("DIFS resetted. Current job lists (first 10 items): %s" % str(list(self.job)[:10]))

    def resetJob(self):
        while self.job and 'send data' not in self.job[0]:
            self.job.popleft()
        self.job.extendleft(self.CSMA_pattern_pre()[::-1])
        logging.info("Job resetted. Current job lists (first 10 items): %s" % str(list(self.job)[:10]))

    def defer(self):
        self.job.extendleft(['DEF'] * (configuration.dataFrameSlotSize+configuration.SIFSSlotSize))
        logging.info("Job deferred. Current job lists (first 10 items): %s" % str(list(self.job)[:10]))

    def run(self, receivedMessage={}):

        message = receivedMessage.copy()
        self.slotIndex += 1
        job = self.job
        title = 'Tx %s status (slot # %d): ' % (self.name, self.slotIndex)

        for hidden_node in self.hidden:
            if hidden_node in message:
                logging.info(title + 'Message (%s) from hidden node %s \"received\". Delete it.' % (message[hidden_node], hidden_node))
                del message[hidden_node]

        # if traffic arrives, append job queue and update next traffic time
        if self.slotIndex >= self.nextTrafficSlot:
            logging.info(title + "New packet (designated slot # %d) arrived by slot # %d." % (self.nextTrafficSlot, self.slotIndex))
            if len(self.job) < configuration.simulationSlot - self.slotIndex:
                job.extend(self.CSMA_pattern())
            else:
                logging.info(title + "Job of Tx %s not extended because the current job buffer (%d) is big enough." % (self.name, len(job)))
            self.nextTrafficTime += self.generate_traffic_interval()
            self.nextTrafficSlot = math.ceil(self.nextTrafficTime / configuration.slotDuration)
            self.packetNumber += 1

        # for each time, we check the job queue to decide what to do
        logging.info(title + 'Job content (job[0]): \"%s\"' % (job[0] if job else 'None'))
        if not job:
            pass
        elif not self.sending() and len(message)==1 and 'CTS' in message.values()[0] and str(configuration.ctsFrameSlotSize) in message.values()[0] and 'CTS %s' % self.name not in message.values()[0]:
            logging.info(title + 'Other CTS received. Defer transmission.')
            self.collisionCounter += 1
            self.defer()
        elif 'DEF' in job[0]:
            job.popleft()
            logging.info(title + 'Defer transmission.')
        elif 'RTS' in job[0]:
            return job.popleft()
        elif 'CTS' in job[0]:
            job.popleft()
            if len(message)==1:
                m = message.values()[0]
                if 'CTS %s' % self.name in m:
                    if ('CTS %s %d' % (self.name, configuration.ctsFrameSlotSize)) in message.values()[0] and self.ctsBuffer==configuration.ctsFrameSlotSize-1:
                        logging.info(title + 'CTS successfully received! Ready to send data.')
                        self.ctsBuffer = 0
                    else:
                        self.ctsBuffer += 1
                else:
                    logging.info(title + 'Other CTS received. message: %s. Reset job.')
                    self.resetJob()
                    self.collisionCounter += 1
            else:
                # logging.info(title + 'No message / Collision. CTS not received. Message: %s. Reset job.' % str(message))
                logging.info(title + 'No message / Collision. CTS not received. Message: %s. Reset job. Double CW.' % str(message))
                self.backoffTimeMax = configuration.doubleCW(self.backoffTimeMax + 1) - 1
                self.resetJob()
                logging.info('CW doubled. Current CW: %d' % (self.backoffTimeMax + 1))
                self.collisionCounter += 1
        elif job[0] == 'DIFS':
            if not message:
                job.popleft()
            else:
                logging.info(title + 'Expected DIFS, message %s received. Resetting DIFS.' % str(message))
                self.resetDIFS()
                self.collisionCounter += 1
        elif job[0] == 'SIFS':
            if not message:
                job.popleft()
            else:
                logging.info(title + 'Expected SIFS, message %s received. ERROR!' % str(message))
                self.collisionCounter += 1
        elif 'backoff' in job[0]:
            if not message:
                job.popleft()
            else:
                logging.info(title + 'Backoff: message %s received. Resetting job.' % str(message))
                self.resetJob()
                self.collisionCounter += 1
        elif 'send data' in job[0]:
            return job.popleft()
        elif 'ACK' in job[0]:
            job.popleft()
            if len(message) == 1:
                if 'ACK %s %d' % (self.name, configuration.ackFrameSlotSize) in message.values()[0] and (self.ackBuffer==configuration.ackFrameSlotSize-1):
                    logging.info("Tx %s got message: '%s'. Transmission success!" % (self.name, str(message)))
                    self.packetNumberSuccess += 1
                    self.ackBuffer = 0 # reset ackBuffer
                elif 'ACK %s' % self.name in message.values()[0]:
                    self.ackBuffer += 1
            else:
                logging.info('Tx %s does not get ACK. Transmission fail. Retransmitting a packet. Double the CW. Message: %s' % (self.name, str(message)))
                self.job.extendleft(self.CSMA_pattern()[::-1])
                logging.info("Packet resetted. Current job lists (first 10 items): %s" % str(list(self.job)[:10]))
                self.backoffTimeMax = configuration.doubleCW(self.backoffTimeMax+1)-1
                logging.info('CW doubled. Current CW: %d' % (self.backoffTimeMax+1))
                self.collisionCounter += 1
        else:
            logging.info("Unresolved message: %s" % message)
            self.collisionCounter += 1


class Rx(object):
    def __init__(self, name, csEnabled=False):
        self.name = name
        self.job = collections.deque()
        self.slotIndex = 0
        self.packetNumberSuccess = 0
        self.collisionNumber = 0
        self.csEnabled = csEnabled
        self.rtsBuffer = collections.defaultdict(int)
        self.dataBuffer = collections.defaultdict(int)

    def sending(self):
        return self.job and 'send' in self.job[0]

    def run(self, message):
        self.slotIndex += 1
        title = "Rx %s status (slot # %d): " % (self.name, self.slotIndex)

        # sending phase
        if self.job:
            if 'send' in self.job[0]:
                logging.info(title + "Sending out message: \"%s\"" % self.job[0])
                return self.job.popleft()
            elif 'SIFS' in self.job[0]:
                self.job.popleft()
                logging.info(title + "SIFS.")
                return
            else:
                logging.info(title + "Unknown job content: %s" % str(self.job.popleft()))
                return

        # receiving phase
        for name in message:
            logging.info(title + "Received message from Tx %s: \"%s\"" % (name, message[name]))
        messages = [m for m in message.values() if m]
        if len(messages)>1:
            logging.info(title + "Collision!")
            self.collisionNumber += 1
        elif len(message)==0:
            logging.info(title + "No message. Idle.")
        else:
            m = message.values()[0]
            sender = message.keys()[0]
            if 'send data' in m and (str(configuration.dataFrameSlotSize) in m) and (('-> %s' % self.name) in m):
                logging.info(title + "Last frame of data received. Data buffer size: %d" % self.dataBuffer[sender])
                if self.dataBuffer[sender]==configuration.dataFrameSlotSize-1:
                    logging.info('All data received! Transmission success!')
                    self.packetNumberSuccess += 1
                    self.job.extend(['SIFS'] + [('send ACK ' + sender + (' %d from Rx %s' % (i, self.name))) for i in range(1, configuration.ackFrameSlotSize+1)])
                self.dataBuffer[sender] = 0
            elif 'data' in m:
                if ('-> %s' % self.name) in m:
                    self.dataBuffer[sender] += 1
                    logging.info(title + "Data received. Current buffer size: %d" % self.dataBuffer[sender])
                else:
                    logging.info(title + "Data (to other destination) received.")
            elif 'RTS' in m:
                if self.csEnabled:
                    if ('RTS %d -> %s' % (configuration.rtsFrameSlotSize, self.name) in m) and (self.rtsBuffer[sender]==self.slotIndex-1):
                        logging.info(title + 'RTS from %s all received. Clear to send.' % sender)
                        self.rtsBuffer[sender] = 0
                        self.job.extend(['SIFS'] * configuration.SIFSSlotSize)
                        self.job.extend(['send CTS %s %d' % (sender, i) for i in range(1, configuration.ctsFrameSlotSize+1)])
                        self.job.extend(['SIFS'] * configuration.SIFSSlotSize)
                    elif '-> %s' % self.name in m:
                        self.rtsBuffer[sender] = self.slotIndex if ('RTS 1' in m or self.rtsBuffer[sender]==self.slotIndex-1) else 0
                        logging.info('RTS from %s received. Buffer updated. Current buffer: Slot # %d' % (sender, self.rtsBuffer[sender]))
                    else:
                        logging.info(title + 'RTS to other station received.')
                else:
                    logging.info('Carrier Sensing not enabled in Rx. However RTS received. Message: %s' % str(message))
            else:
                logging.info(title + "Other message received: %s" % m)


class Simulator(object):

    def __init__(self):
        pass

    def simulate_CSMACA_a(self, la, lc, cs):

        csEnabled = cs

        txA = Tx(la, "A", "B", csEnabled=csEnabled)
        rxB = Rx('B', csEnabled=csEnabled)
        txC = Tx(lc, "C", "D", csEnabled=csEnabled)
        rxD = Rx('D', csEnabled=csEnabled)
        nodes = [txA, txC, rxB, rxD]

        # collisionCounter = 0
        pairABCounter = 0
        pairCDCounter = 0

        startTime = time.time()
        print ''

        for slotIndex in range(1, configuration.simulationSlot + 1):

            if slotIndex%(configuration.simulationSlot//100)==0:
                progress = slotIndex//(configuration.simulationSlot//100)
                remainingTime = (100-progress)/float(progress)*(time.time()-startTime)
                sys.stdout.write('\rProgress: %d%%. Remaining time: %.0fs' % (progress, remainingTime))

            logging.info("\nSimulator slot #: %d" % slotIndex)

            # fill messages, if anyone has message (in job queue), run them first.
            phase1 = nodes
            phase2 = []
            messages = {}

            logging.info("Sending phase:")
            for node in phase1: # process those sending messages
                if node.sending():
                    messages[node.name] = node.run({})
                else:
                    phase2.append(node)

            logging.info("Messages: %s" % str(messages))
            # if len(messages)>1:
            #     collisionCounter += 1
            if len(messages)==1 and 'A -> B' in messages.values()[0]:
                pairABCounter += 1
            if len(messages)==1 and 'C -> D' in messages.values()[0]:
                pairCDCounter += 1

            logging.info("Receiving phase:")
            for node in phase2: # process those listening messages
                node.run(messages)

        print("\nSimulation Result:")
        print("Final CW: %d" % (txA.backoffTimeMax+1))
        print("")
        print("Packet # of Tx A: %d" % txA.packetNumber)
        print("Packet # of Tx C: %d" % txC.packetNumber)
        print("Successful packet # of Tx A: %d" % txA.packetNumberSuccess)
        print("Successful packet # of Tx C: %d" % txC.packetNumberSuccess)
        print("Successful packet # of Rx B: %d" % rxB.packetNumberSuccess)
        print("Successful packet # of Rx D: %d" % rxD.packetNumberSuccess)
        print("")
        print("Throughput of Tx A: %.2f Mbps" % (txA.packetNumberSuccess * configuration.dataFrameSize / configuration.simulationTime))
        print("Throughput of Tx C: %.2f Mbps" % (txC.packetNumberSuccess * configuration.dataFrameSize / configuration.simulationTime))
        print("Throughput of Rx B: %.2f Mbps" % (rxB.packetNumberSuccess * configuration.dataFrameSize / configuration.simulationTime))
        print("Throughput of Rx D: %.2f Mbps" % (rxD.packetNumberSuccess * configuration.dataFrameSize / configuration.simulationTime))
        print("")
        print("# of collisions of Tx A: %d" % txA.collisionCounter)
        print("# of collisions of Tx C: %d" % txC.collisionCounter)
        print("")
        print("# of slots occupied by pair A -> B: %d" % pairABCounter)
        print("# of slots occupied by pair C -> D: %d" % pairCDCounter)
        if pairCDCounter>0:
            print("Fairness Index: %.2f" % (float(pairABCounter)/pairCDCounter))
        else:
            print("Could not calculate FI.")

    def simulate_CSMACA_b(self, la, lc, cs):

        csEnabled = cs

        txA = Tx(la, "A", "B", csEnabled=csEnabled, hidden=['C'])
        rxB = Rx('B', csEnabled=csEnabled)
        txC = Tx(lc, "C", "B", csEnabled=csEnabled, hidden=['A'])
        nodes = [txA, txC, rxB]

        # collisionCounter = 0
        pairABCounter = 0
        pairCBCounter = 0

        startTime = time.time()
        print ''

        for slotIndex in range(1, configuration.simulationSlot + 1):

            if slotIndex%(configuration.simulationSlot//100)==0:
                progress = slotIndex//(configuration.simulationSlot//100)
                remainingTime = (100-progress)/float(progress)*(time.time()-startTime)
                sys.stdout.write('\rProgress: %d%%. Remaining time: %.0fs' % (progress, remainingTime))

            logging.info("\nSimulator slot #: %d" % slotIndex)

            # fill messages, if anyone has message (in job queue), run them first.
            phase1 = nodes
            phase2 = []
            messages = {}

            logging.info("Sending phase:")
            for node in phase1: # process those sending messages
                if node.sending():
                    messages[node.name] = node.run({})
                else:
                    phase2.append(node)

            logging.info("Messages: %s" % str(messages))
            # if len(messages)>1:
            #     collisionCounter += 1
            if len(messages)==1 and 'A -> B' in messages.values()[0]:
                pairABCounter += 1
            if len(messages)==1 and 'C -> B' in messages.values()[0]:
                pairCBCounter += 1

            logging.info("Receiving phase:")
            for node in phase2: # process those listening messages
                node.run(messages)

        print("\nSimulation Result:")
        print("Final CW of A: %d" % (txA.backoffTimeMax+1))
        print("Final CW of C: %d" % (txC.backoffTimeMax+1))
        print("")
        print("Packet # of Tx A: %d" % txA.packetNumber)
        print("Packet # of Tx C: %d" % txC.packetNumber)
        print("Successful packet # of Tx A: %d" % txA.packetNumberSuccess)
        print("Successful packet # of Tx C: %d" % txC.packetNumberSuccess)
        print("Successful packet # of Rx B: %d" % rxB.packetNumberSuccess)
        print("")
        print("Throughput of Tx A: %.2f Mbps" % (txA.packetNumberSuccess * configuration.dataFrameSize / float(configuration.simulationTime)))
        print("Throughput of Tx C: %.2f Mbps" % (txC.packetNumberSuccess * configuration.dataFrameSize / float(configuration.simulationTime)))
        print("Throughput of Rx B: %.2f Mbps" % (rxB.packetNumberSuccess * configuration.dataFrameSize / float(configuration.simulationTime)))
        print("")
        print("# of collisions of Tx A: %d" % txA.collisionCounter)
        print("# of collisions of Tx C: %d" % txC.collisionCounter)
        print("")
        print("# of slots occupied by pair A -> B: %d" % pairABCounter)
        print("# of slots occupied by pair C -> B: %d" % pairCBCounter)
        if pairCBCounter>0:
            print("Fairness Index: %.2f" % (float(pairABCounter)/pairCBCounter))
        else:
            print("Could not calculate FI.")

    def testAll(self):

        testcases = [[50, 50, False], [100, 100, False], [200, 200, False], [300, 300, False],\
                     [100, 50, False], [200, 100, False], [400, 200, False], [600, 300, False],\
                     [50, 50, True], [100, 100, True], [200, 200, True], [300, 300, True],\
                     [100, 50, True], [200, 100, True], [400, 200, True], [600, 300, True]\
                    ]

        print '\n\n'
        print '========== A ==========\n'
        for la, lb, cs in testcases:
            print '\n----------\nCurrent test case: %d, %d, %s.' % (la, lb, 'CS Enabled' if cs else 'CS Disabled')
            Simulator().simulate_CSMACA_a(la, lb, cs)
            print 'Test finished.\n----------\n'

        print '\n\n'
        print '========== B ==========\n'
        for la, lb, cs in testcases:
            print '\n----------\nCurrent test case: %d, %d, %s.' % (la, lb, 'CS Enabled' if cs else 'CS Disabled')
            Simulator().simulate_CSMACA_b(la, lb, cs)
            print 'Test finished.\n----------\n'

        os.system('say "Test has finished"')

Simulator().testAll()