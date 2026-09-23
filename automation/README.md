# Configuration Generator

Cisco IOS configurations for this network are generated from a single source of
truth rather than written by hand.

```
inventory.yml  ──┐
                 ├──►  render.py  ──►  ../configs/*.cfg
templates/*.j2 ──┘
```

## Why

Zone SN2 was configured manually, command by command, to establish a verified
baseline. Repeating the same twenty-odd commands across the remaining eight
devices by hand invites transcription errors, and any later change to the
addressing plan would have to be applied nine times without missing one.

The inventory holds the design; the templates hold the syntax; the renderer
combines them. A change to a VLAN number or an SVI address is made once.

## Usage

```bash
python3 automation/render.py            # all zones
python3 automation/render.py SN1 SN3    # selected zones
```

Requires `pyyaml` and `jinja2`.

## Files

| Path | Role |
|---|---|
| `inventory.yml` | The design: zones, VLANs, addresses, per-device trunk ports |
| `templates/access_switch.j2` | Switch configuration: VLANs, trunks, access ports, SVI, STP |
| `templates/zone_router.j2` | Router LAN side: 802.1Q sub-interfaces and DHCP |
| `render.py` | Loads the inventory, renders the templates, writes `configs/` |

## What the renderer computes

Access ports are not listed in the inventory. The renderer derives them: every
FastEthernet port that is *not* a trunk becomes an access port in the user VLAN,
and the resulting port numbers are collapsed into the smallest set of contiguous
`interface range` statements.

For `SN3-SW1`, whose trunks are on ports 1, 3 and 4, this yields:

```
interface fastEthernet 0/2
interface range fastEthernet 0/5-24
```

Listing access ports by hand would mean recomputing that set whenever a cable
moves.

## Validation

Zone SN2 is present in the inventory although it was built by hand. Rendering it
reproduces the manual configuration exactly, which is how the generator was
verified before being trusted with the other two zones.

Generating a configuration for a device you already know, and comparing, is the
standard way to gain confidence in a generator before pointing it at an estate
you do not want to break.

## Scope

The renderer covers what stages A2 to A4 configure: VLANs, trunking, access
ports, management interfaces, spanning-tree roles, inter-VLAN routing and DHCP.

Transit-link addressing (stage A1) is deliberately excluded. Those interfaces
were configured during topology bring-up and are not part of the repeated
per-zone pattern.

## Applying the output

Packet Tracer does not accept SSH connections from the host, so delivery is
manual: open the generated file and paste its contents into the device CLI.

On real equipment this step would be handled by Ansible, Netmiko or Nornir
against the same rendered output.
