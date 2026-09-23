# Checks

```bash
pytest tests/ -v
```

Two suites, run on every push by `.github/workflows/validate.yml`.

## `test_inventory.py` — the design

Properties the addressing plan depends on, checked before anything is rendered:

| Check | What it prevents |
|---|---|
| VLAN ids unique | The same identifier reused for two purposes |
| VLAN id equals third octet | Addresses that no longer read without a lookup table |
| Gateway is the first host address | Silent drift from the documented convention |
| SVI inside its own subnet | A switch unreachable through its management VLAN |
| User subnets hold ≥ 200 hosts | The sizing requirement that produced the `/24` |
| No two subnets overlap | Ambiguous routing |
| One root and one secondary per zone | A Layer 2 topology decided by MAC address |
| The uplink switch is the root | Egress traffic crossing the zone twice |
| Trunks are symmetric | A one-sided trunk: link up, tagged frames dropped |
| `/30` endpoints from the same block | A link that carries traffic and cannot be used |
| Routers form a closed triangle | A chain, where the middle router is a single point of failure |
| Router-ids present and unique | An OSPF identity that changes when an interface does |
| No wireless secrets committed | Credentials in a public repository |
| Wireless is WPA2 with AES | Silently falling back to deprecated TKIP |

## `test_rendered_configs.py` — the translation into IOS

The inventory may be correct while the renderer is wrong. These render from the
current inventory and inspect the output:

| Check | What it prevents |
|---|---|
| One file per device, correct hostname | A configuration applied to the wrong switch |
| Trunk ports match the inventory | A trunk on the wrong port, isolating whatever is plugged in |
| Every port is either trunk or access | A port left in VLAN 1, open to any device |
| Trunks carry only the two VLANs in use | Unnecessary flooding, and a path for VLAN hopping |
| SVI and default gateway present | A switch that answers only inside its own subnet |
| Spanning-tree role applied | A zone with no deliberate root |
| `encapsulation dot1Q` matches the VLAN | Sub-interfaces bound to the wrong VLAN |
| Physical interface unaddressed | An address on the trunk itself |
| DHCP excludes the reserved range | Allocation beginning at the gateway's own address |
| Management VLAN not served by DHCP | A switch losing its address to an expired lease |
| No credentials in generated files | Secrets reaching version control |

## Fault injection

Each check was confirmed against a deliberately broken inventory: moving an SVI
outside its subnet, declaring two root bridges in one zone, breaking trunk
symmetry, drawing `/30` endpoints from different blocks, and committing a real
wireless key. Every fault was caught by the intended check and by no other.
