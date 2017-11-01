import math

# Simulation parameters
# basic units: bit, us, slot, bpus
byte = 8
dataFrameSize = 1500 * byte # 1500
ackFrameSize = 30 * byte
rtsFrameSize = 30 * byte
ctsFrameSize = 30 * byte
slotDuration = 20
SIFSDuration = 10
DIFSDuration = 40
transmissionRate = 6
CW0 = 4
CWmax = 1024
lA = map(lambda x: float(x)/(10**6), [50, 100, 200, 300])
lC = lA
simulationTime = 10.0 * (10 ** 6) # 10 * (10 ** 6)

# Derived parameters
# basic units: slot
ackFrameSlotSize = ackFrameSize // transmissionRate // slotDuration
print 'Parameter: ackFrameSlotSize = %d' % ackFrameSlotSize
rtsFrameSlotSize = rtsFrameSize // transmissionRate // slotDuration
print 'Parameter: rtsFrameSlotSize = %d' % ackFrameSlotSize
ctsFrameSlotSize = ctsFrameSize // transmissionRate // slotDuration
print 'Parameter: ctsFrameSlotSize = %d' % ackFrameSlotSize
dataFrameSlotSize = dataFrameSize // transmissionRate // slotDuration
print 'Parameter: dataFrameSlotSize = %d' % dataFrameSlotSize
SIFSSlotSize = int(math.ceil(SIFSDuration / float(slotDuration)))
print 'Parameter: SIFSSlotSize = %d' % SIFSSlotSize
DIFSSlotSize = int(math.ceil(DIFSDuration / float(slotDuration)))
print 'Parameter: DIFSSlotSize = %d' % DIFSSlotSize
simulationSlot = int(math.ceil(simulationTime / float(slotDuration)))
print 'Parameter: simulationSlot = %d' % simulationSlot

def doubleCW(cw):
    res = cw * 2
    return cw if res>CWmax else res