import csv
from engine import settle
from decimal import Decimal
from pathlib import Path
root=Path(__file__).parent
with (root/'commission_comparison.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['daily_matches','entry_per_player_usd','commission','annual_pool_usd','annual_platform_gross_usd','monthly_platform_gross_30d_usd'])
 for matches in [100,250,500,1000,2500,5000]:
  for rate in ['0.16','0.20','0.25','0.30']:
   per=settle([500,500],Decimal(rate))['platform_cents']/100
   w.writerow([matches,5,rate,matches*10*365,round(matches*per*365,2),round(matches*per*30,2)])
print('commission comparison created')
