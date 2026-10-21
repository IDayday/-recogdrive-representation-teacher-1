"""Use the verified terminal client with third-batch command/output paths."""
from r3_common import *
import argparse


def main(args):
    sys.path.insert(0, str(BATCH2/'code'))
    from r2_remote import execute
    path=Path(args.command_file).resolve(); assert path.is_relative_to(ROOT)
    result=execute(args.job, path.read_text(), timeout=args.timeout)
    atomic(ROOT/args.output, result)
    print(json.dumps({k:result[k] for k in ['status','job','exit_code','seconds']}),flush=True)
    assert result['exit_code']==0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',required=True);p.add_argument('--command-file',required=True)
    p.add_argument('--output',required=True);p.add_argument('--timeout',type=int,default=50)
    main(p.parse_args())
