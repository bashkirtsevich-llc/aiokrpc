# Asyncio Kademlia RPC-server
[![Build Status](https://travis-ci.org/bashkirtsevich-llc/aiokrpc.svg?branch=master)](https://travis-ci.org/bashkirtsevich-llc/aiokrpc)

Kademlia protocol based RPC-server.

## Example

```python
import asyncio

loop = asyncio.get_event_loop()

udp = UDPServer()
udp.run("0.0.0.0", 12346, loop=loop)

app = KRPCServer(server=udp, loop=loop)

@app.callcack(arg_schema={"id": {"type": "integer", "required": True}})
def ping(addr, id):
    print(addr, id)
    return {"id": id}

if __name__ == '__main__':
    loop.run_forever()
```