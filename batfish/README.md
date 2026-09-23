# Formal analysis with Batfish

The checks in `tests/` verify that the configurations say what they should.
Batfish verifies what they *do*: it parses the device configurations, builds a
model of the network's forwarding behaviour, and answers questions about it
without touching any equipment.

The difference matters. A missing `network` statement under OSPF leaves every
check in `tests/` passing — nothing is written incorrectly — while a whole zone
becomes unreachable. That fault is only visible once the devices are considered
together.

## Input

Batfish reads complete `running-config` output, not the command sequences in
`configs/`. Those are lists of commands to type; these are the resulting state.

```
batfish/configs/
├── SN1-RTR.cfg
├── SN2-RTR.cfg
├── SN3-RTR.cfg
└── ISP.cfg
```

Captured with:

```
enable
terminal length 0
show running-config
```

## Running

Batfish itself runs as a container:

```bash
docker run --name batfish -p 9997:9997 -p 9996:9996 batfish/allinone
pip install pybatfish
python3 batfish/analyse.py
```

## What it answers

- which prefixes each router can reach, and by which path
- whether any route leads nowhere
- what becomes unreachable if a given link fails
- whether an access list blocks more than intended
- whether all routers hold a consistent view of the topology
