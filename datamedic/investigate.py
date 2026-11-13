"""Run an investigation and emit the complete reviewable JSON trace."""
import argparse
import asyncio
import json
from datamedic.agent.models import Alert
from datamedic.agent.graph import investigate
from datamedic.agent.transport import MCPTransport

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alert',default='Recorded payment value dropped for the selected purchase date; investigate payment coverage and operational evidence.')
    parser.add_argument('--date',default='2018-08-15')
    parser.add_argument('--budget',type=int,default=12)
    args=parser.parse_args()
    alert=Alert(text=args.alert,purchase_date=args.date,budget=args.budget)
    print(json.dumps(asyncio.run(investigate(alert,MCPTransport())),indent=2))

if __name__=='__main__':
    main()
