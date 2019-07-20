# Asyncio Kademlia RPC-server
[![Build Status](https://travis-ci.org/bashkirtsevich-llc/aiokrpc.svg?branch=master)](https://travis-ci.org/bashkirtsevich-llc/aiokrpc)

Kademlia protocol based RPC-server.

## Example

```python
app = KRPCServer()

@app.callcack(arg_schema={"id": {"type": "integer", "required": True}})
def ping(addr, id):
    print(addr, id)
    return {"id": id}

if __name__ == '__main__':
    app.run("0.0.0.0", 12346)

```