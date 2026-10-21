"""Install the frozen source snapshot into a separate writable workspace."""
import argparse
from continuation.layout import materialize

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True)
    a=p.parse_args();print(materialize(a.workspace))

if __name__=='__main__':main()
