"""EtsyClient.create_draft needs no OwnerGrant, no DB, and trusts the constructor's phase string.
Recording transport only: no socket is opened."""
from brambleloop.integrations import etsy as E
from brambleloop.integrations.http import Response
import inspect
sent = []
class Rec:
    def request(self, method, url, **kw):
        sent.append((method, url)); return Response(status=200, body={"listing_id": 123}, headers={}) if 'status' in inspect.signature(Response).parameters else None
creds = E.Credentials(api_key="k", access_token="t", shop_id="S")
payload = E.build_payload(title="Probe", description="d", price_cad=1.0, tags=["a"], materials=["yarn"])
c = E.EtsyClient(Rec(), credentials=creds, phase="production", owner_authorised=True)  # no db, no grant, no recorded phase
try:
    print("create_draft ->", c.create_draft(payload))
except Exception as e:
    print("raised", type(e).__name__, str(e)[:150])
print("requests that reached the transport:", sent)
c2 = E.EtsyClient(Rec(), credentials=creds, phase="production", owner_authorised=True)
try: c2.publish(payload=payload, filename="x.pdf", data=b"x")
except Exception as e: print("publish without grant ->", type(e).__name__, str(e)[:100])
