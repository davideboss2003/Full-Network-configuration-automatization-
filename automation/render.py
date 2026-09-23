#!/usr/bin/env python3
"""Render Cisco IOS configurations for the PPRC network.

Reads automation/inventory.yml, applies the Jinja2 templates in
automation/templates/, and writes one .cfg file per device into configs/.

    python3 automation/render.py            # render every zone
    python3 automation/render.py SN1 SN3    # render selected zones only

The inventory is the single source of truth. Generated files are overwritten
on every run, so changes belong in the inventory, never in configs/.
"""

import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "automation" / "inventory.yml"
TEMPLATES = ROOT / "automation" / "templates"
OUTPUT = ROOT / "configs"


def contiguous_ranges(numbers):
    """Collapse a sorted set of port numbers into contiguous ranges.

    {3, 5, 6, 7, 9} -> [{'first': 3, 'last': 3}, {'first': 5, 'last': 7}, ...]

    Used to turn "every port that is not a trunk" into the smallest set of
    `interface range` statements, rather than one block per port.
    """
    ranges, start, previous = [], None, None
    for n in sorted(numbers):
        if start is None:
            start = previous = n
        elif n == previous + 1:
            previous = n
        else:
            ranges.append({"first": start, "last": previous})
            start = previous = n
    if start is not None:
        ranges.append({"first": start, "last": previous})
    return ranges


def access_ranges_for(switch, defaults):
    """Every FastEthernet port that is not carrying a trunk."""
    first, last = defaults["access_ports"]["fastethernet"]
    trunk_ports = {t["port"] for t in switch["trunks"]}
    return contiguous_ranges(set(range(first, last + 1)) - trunk_ports)


def dhcp_exclusion(zone, defaults):
    """First and last address of the reserved range in a user subnet."""
    network = zone["user_vlan"]["subnet"].rsplit(".", 1)[0]
    return f"{network}.1", f"{network}.{defaults['dhcp_reserved_upto']}"


def main(selected_zones):
    inventory = yaml.safe_load(INVENTORY.read_text())
    defaults = inventory["defaults"]

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,   # fail loudly on a typo in the inventory
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    switch_tpl = env.get_template("access_switch.j2")
    router_tpl = env.get_template("zone_router.j2")

    OUTPUT.mkdir(exist_ok=True)
    written = []

    for name, zone in inventory["zones"].items():
        if selected_zones and name not in selected_zones:
            continue

        for switch in zone["switches"]:
            text = switch_tpl.render(
                zone=zone,
                sw=switch,
                defaults=defaults,
                access_ranges=access_ranges_for(switch, defaults),
            )
            path = OUTPUT / f"{switch['hostname']}.cfg"
            path.write_text(text)
            written.append(path)

        first_excluded, last_excluded = dhcp_exclusion(zone, defaults)
        text = router_tpl.render(
            zone=zone,
            defaults=defaults,
            dhcp_first_excluded=first_excluded,
            dhcp_last_excluded=last_excluded,
        )
        path = OUTPUT / f"{zone['router']['hostname']}-lan.cfg"
        path.write_text(text)
        written.append(path)

    for path in written:
        print(f"  {path.relative_to(ROOT)}")
    print(f"\n{len(written)} configurations written to {OUTPUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main(set(sys.argv[1:]))
