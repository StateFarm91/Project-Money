from j_sec_common import *
import re
c=client(); login(c)
for p in ["/api/cc/home","/api/cc/operations","/api/cc/account","/api/cc/emergency"]:
    t=c.get(p).text
    print(p, [t[max(0,m.start()-40):m.end()+30] for m in re.finditer("BRAMBLELOOP_",t)][:2])
