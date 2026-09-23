# Three-Building Campus Network

A Cisco campus network for an institution spread across three buildings: segmented
with VLANs, made redundant at both Layer 2 and Layer 3, addressed automatically,
and published to the outside through a DMZ.

Two thirds of the device configurations are **generated from a single YAML
inventory** rather than typed by hand.

![Network topology](docs/latex/img/topologie-generala.png)

---

## What it implements

| | |
|---|---|
| **Segmentation** | Two VLANs per building — users and management — carried over 802.1Q trunks |
| **Layer 2 redundancy** | Three switches per building in a triangle, resolved by Spanning Tree with an explicitly placed root |
| **Layer 3 redundancy** | Three routers in a full mesh running OSPF area 0, producing equal-cost paths |
| **Inter-VLAN routing** | 802.1Q sub-interfaces on each building router |
| **Addressing** | DHCP served by the routers; infrastructure static and excluded from the pools |
| **Wireless** | One access point per building, WPA2-PSK with AES, sharing the user VLAN with cabled hosts |
| **DMZ** | HTTP, FTP, DNS and mail on public addresses behind a dedicated switch and VLAN |
| **External link** | Point-to-point fibre to a provider router, with a simulated external network |

## Addressing

| Block | Purpose |
|---|---|
| `172.16.0.0/16` | Intranet — subnetted into `/24` user and management VLANs |
| `172.16.255.0/24` | Point-to-point router links, subnetted into `/30` |
| `210.1.1.64/27` | DMZ, public addresses |
| `210.1.1.32/27` | Provider link |

The VLAN identifier equals the third octet, so `172.16.20.55` reads as
*zone 2, user VLAN* without a lookup table.

| Zone | Router | User VLAN | Management VLAN |
|---|---|---|---|
| Subnet 1 | `SN1-RTR` | 10 → `172.16.10.0/24` | 110 → `172.16.110.0/24` |
| Subnet 2 | `SN2-RTR` | 20 → `172.16.20.0/24` | 120 → `172.16.120.0/24` |
| Subnet 3 | `SN3-RTR` | 30 → `172.16.30.0/24` | 130 → `172.16.130.0/24` |

---

## Configuration generation

One building was configured by hand to establish a verified baseline. The
remaining two were generated:

```
automation/inventory.yml   ──┐
                             ├──►  render.py  ──►  configs/*.cfg
automation/templates/*.j2  ──┘
```

```bash
python3 automation/render.py            # all zones
python3 automation/render.py SN1 SN3    # selected zones
```

Twelve configurations from 144 lines of inventory, in under a tenth of a second.

**Access ports are computed, not listed.** Any port not carrying a trunk becomes
an access port in the user VLAN, and the resulting numbers are collapsed into the
fewest contiguous `interface range` statements — so a switch whose trunks sit on
ports 1, 3 and 4 yields `Fa0/2` alone plus `Fa0/5-24`.

**The generator was validated against the hand-built zone.** That zone is still in
the inventory; rendering it reproduces the manual configuration exactly. The
resulting networks also converge identically:

| | Built by hand | Generated |
|---|---|---|
| Root bridge priority | 24596 | 24586 |
| Blocked port | `Fa0/2` `Altn BLK` | `Fa0/2` `Altn BLK` |
| Root port | `Fa0/4` `Root FWD` | `Fa0/4` `Root FWD` |

The difference of ten is the VLAN identifier.

Jinja2 is the engine Ansible uses internally, so the templates carry over to an
Ansible workflow unchanged. Delivery here is manual only because Packet Tracer
accepts no inbound SSH.

---

## Repository

```
docs/latex/     Technical report (LaTeX source and figures)
automation/     Inventory, Jinja2 templates, renderer
configs/        Generated device configurations
topology/       Packet Tracer file
```

## Report

`docs/latex/PPRC-Muresan-Davide.tex` covers the design and every configuration
step, with the verification output from the running network — spanning-tree
convergence, OSPF adjacencies and routing tables, DHCP leases, DNS resolution.

It also records what was learned in the process: why a ping failing in one
direction and succeeding in the other locates a missing default gateway, and why
a `TTL` of 254 rather than 255 proves a packet was routed rather than switched.

---

Built in Cisco Packet Tracer · Muresan Davide-Andrei · Technical University of Cluj-Napoca
