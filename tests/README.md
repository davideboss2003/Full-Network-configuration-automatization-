# Checks

```bash
pytest tests/ -v
```

Three suites, run on every push by `.github/workflows/validate.yml`.

They test different things, and the distinction matters when one fails:

| Suite | Subject | Answers |
|---|---|---|
| `test_render_functions.py` | a function | is the algorithm correct? |
| `test_inventory.py` | data | is the design coherent with itself? |
| `test_rendered_configs.py` | generated files | did the design translate correctly into IOS? |

Only the first is a unit test in the usual sense. The other two are
configuration validation — the plan and its output are data, not logic, and a
fault in either produces a network that is wrong without anything having
crashed.

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
| Port-security policy is coherent | A limit so high flooding still succeeds, learning that is lost on reload, or an access-point limit no higher than a workstation's |
| One access point per zone | Two ports treated as uplinks for wireless clients |

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
| Committed output carries placeholders | A real credential reaching version control |
| Every device has `enable secret` | An unauthenticated device: console access is full access |
| Passwords hashed, not stored reversibly | `password` where `secret` was meant |
| Two privilege levels defined | One account used for both inspection and change |
| Remote access restricted to SSH v2 | Telnet, which carries credentials in clear text |
| Domain name set before key generation | RSA generation failing silently |
| Sessions time out | An unattended session anyone can walk up to |
| Console authenticated too | vty locked while physical access is free |
| Login banner present | — |
| Access ports carry port security | A port accepting unlimited MAC addresses, and therefore a flooding attack |
| Trunks carry none | A limit on a link that legitimately sees hundreds of addresses |
| The access-point port allows more | Wireless clients blocked as they associate |

## `test_render_functions.py` — the algorithm

`contiguous_ranges` is the only real logic in the generator: it turns "every
port that is not a trunk" into the fewest `interface range` statements. Trunks
on ports 1, 3 and 4 must leave port 2 alone and ports 5–24 whole.

It is tested directly rather than only through its output, because a fault here
produces configurations that look plausible while leaving ports unconfigured.
The suite covers empty input, a single port, consecutive ports, gaps, isolated
ports between ranges, unsorted input, and two properties that must hold for any
trunk layout: every input port appears in exactly one range, and no trunk port
is ever emitted as access.

## Fault injection

Each check was confirmed against deliberately broken input: an SVI moved outside
its subnet, two root bridges in one zone, an asymmetric trunk, `/30` endpoints
drawn from different blocks, a committed wireless key, a removed `enable secret`,
an account stored with a reversible password, telnet re-enabled, a session left
without a timeout, an unauthenticated console, and an RSA key generated before
the domain name was set.

**One check failed to catch its fault.** `test_every_device_requires_a_privileged_password`
searched the whole file for `enable secret`, and the string also appears in an
explanatory comment — so the check passed with the command deleted. It now reads
configuration lines only, through the `commands()` helper.

That is the reason for injecting faults rather than trusting a green run: a
check that cannot fail is worse than no check, because it is believed.

A second gap appeared the same way. Limiting the access-point port to two
addresses — enough to block wireless clients as they join — left every check
passing, because the output checks compare against the inventory and follow it
wherever it goes. Constraining what the inventory may say needs its own check,
which is what `test_port_security_policy_is_coherent` does.

The distinction is worth keeping: **output checks verify consistency, policy
checks verify intent.** Without the second kind, the network can be broken by
editing the source of truth while everything stays green.
