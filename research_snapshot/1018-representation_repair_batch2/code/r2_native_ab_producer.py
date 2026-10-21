"""Publish training A/B only after the independent sampler-cache contract passes."""
from r2_common import *
from r2_resume_support import register_once


def main():
    while not (ROOT/'provenance/NATIVE_CACHE_CONTRACT_PASS.json').exists():time.sleep(15)
    base=ROOT/'runs/native_training_ab_v1';handler='code/r2_native_training_ab.py'
    if not (base/'tasks.json').exists():atomic(base/'tasks.json',[dict(id='native_training_ab_v1')]);atomic(base/'producer.json',dict(complete=True,tasks=1,time=stamp()))
    register_once(dict(name='cached_native_training_bitwise_ab',path=str(base.relative_to(ROOT)),handler=handler,handler_sha256=sha(ROOT/handler),kind='custom',priority=6))


if __name__=='__main__':main()
