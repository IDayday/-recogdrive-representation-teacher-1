"""Spawn-safe scoring initialization; no global installation or old mount assumptions."""
import os
from continuation.layout import Runtime

def initialize_score():
    runtime=Runtime(os.environ['RECOGDRIVE_CONTINUATION_PATHS'],os.environ['RECOGDRIVE_CONTINUATION_WORKSPACE'])
    runtime.bootstrap();runtime.setup('scores/'+str(os.getpid()),threads=1)
