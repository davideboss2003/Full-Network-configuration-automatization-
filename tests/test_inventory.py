"""Checks on the design itself, before any configuration is rendered.

These encode the invariants the addressing plan relies on. A change to
inventory.yml that breaks one of them fails here rather than on a device.
"""

import ipaddress
from collections import Counter

import pytest
import yaml

from conftest import INVENTORY


def test_vlan_ids_are_unique_across_the_estate(inventory):
    """A VLAN identifier must not be reused for two different purposes."""
    ids = []
    for zone in inventory["zones"].values():
        ids += [zone["user_vlan"]["id"], zone["mgmt_vlan"]["id"]]

    duplicates = [vid for vid, n in Counter(ids).items() if n > 1]
    assert not duplicates, f"VLAN ids used more than once: {duplicates}"


def test_vlan_id_matches_third_octet(inventory):
    """The plan's central convention: 172.16.20.x belongs to VLAN 20.

    If this ever fails, an address can no longer be read without a lookup
    table, and a port in the wrong VLAN stops being obvious.
    """
    for name, zone in inventory["zones"].items():
        for kind in ("user_vlan", "mgmt_vlan"):
            vlan = zone[kind]
            third_octet = int(vlan["subnet"].split(".")[2])
            assert vlan["id"] == third_octet, (
                f"{name} {kind}: VLAN {vlan['id']} but subnet {vlan['subnet']}"
            )


def test_gateway_is_the_first_host_address(inventory):
    for name, zone in inventory["zones"].items():
        for kind in ("user_vlan", "mgmt_vlan"):
            vlan = zone[kind]
            network = ipaddress.ip_network(f"{vlan['subnet']}/{vlan['mask']}")
            expected = str(next(network.hosts()))
            assert vlan["gateway"] == expected, (
                f"{name} {kind}: gateway {vlan['gateway']}, expected {expected}"
            )


def test_switch_addresses_fall_inside_their_management_subnet(inventory):
    """An SVI outside its own VLAN's subnet is unreachable and easy to miss."""
    for name, zone in inventory["zones"].items():
        network = ipaddress.ip_network(
            f"{zone['mgmt_vlan']['subnet']}/{zone['mgmt_vlan']['mask']}"
        )
        for switch in zone["switches"]:
            address = ipaddress.ip_address(switch["mgmt_ip"])
            assert address in network, (
                f"{switch['hostname']}: {address} is outside {network}"
            )


def test_switch_addresses_are_unique(inventory):
    addresses = [
        sw["mgmt_ip"] for z in inventory["zones"].values() for sw in z["switches"]
    ]
    duplicates = [a for a, n in Counter(addresses).items() if n > 1]
    assert not duplicates, f"management addresses assigned twice: {duplicates}"


def test_user_subnets_hold_at_least_200_hosts(inventory):
    """The sizing requirement that produced the /24 choice."""
    for name, zone in inventory["zones"].items():
        network = ipaddress.ip_network(
            f"{zone['user_vlan']['subnet']}/{zone['user_vlan']['mask']}"
        )
        usable = network.num_addresses - 2
        assert usable >= 200, f"{name}: {network} offers {usable} hosts, need 200"


def test_no_two_subnets_overlap(inventory):
    networks = []
    for zone in inventory["zones"].values():
        for kind in ("user_vlan", "mgmt_vlan"):
            vlan = zone[kind]
            networks.append(
                (
                    f"{zone['label']} VLAN {vlan['id']}",
                    ipaddress.ip_network(f"{vlan['subnet']}/{vlan['mask']}"),
                )
            )
    for link in inventory["transit_links"]:
        networks.append((f"transit {link['subnet']}", ipaddress.ip_network(link["subnet"])))

    for i, (name_a, net_a) in enumerate(networks):
        for name_b, net_b in networks[i + 1:]:
            assert not net_a.overlaps(net_b), f"{name_a} overlaps {name_b}"


def test_each_zone_has_exactly_one_root_and_one_secondary(inventory):
    """Two roots, or none, and the Layer 2 topology is decided by MAC address."""
    for name, zone in inventory["zones"].items():
        roles = Counter(sw["stp"] for sw in zone["switches"])
        assert roles["primary"] == 1, f"{name}: {roles['primary']} root primary"
        assert roles["secondary"] == 1, f"{name}: {roles['secondary']} root secondary"


def test_the_uplink_switch_is_the_root(inventory):
    """Placing the root away from the router makes egress traffic cross the
    zone twice."""
    for name, zone in inventory["zones"].items():
        router = zone["router"]["hostname"]
        for switch in zone["switches"]:
            connects_to_router = any(t["to"] == router for t in switch["trunks"])
            if connects_to_router:
                assert switch["stp"] == "primary", (
                    f"{switch['hostname']} holds the uplink to {router} "
                    f"but is '{switch['stp']}' rather than root primary"
                )


def test_trunk_ports_are_not_declared_twice_on_a_switch(inventory):
    for zone in inventory["zones"].values():
        for switch in zone["switches"]:
            ports = [t["port"] for t in switch["trunks"]]
            duplicates = [p for p, n in Counter(ports).items() if n > 1]
            assert not duplicates, f"{switch['hostname']}: port {duplicates} twice"


def test_trunks_are_symmetric(inventory):
    """If A trunks towards B, B must trunk back towards A.

    A one-sided trunk leaves the other end as an access port: the link comes
    up, and every tagged frame is silently dropped.
    """
    for name, zone in inventory["zones"].items():
        declared = {
            (sw["hostname"], t["to"])
            for sw in zone["switches"]
            for t in sw["trunks"]
        }
        switches = {sw["hostname"] for sw in zone["switches"]}

        for source, target in declared:
            if target not in switches:      # uplink to the router
                continue
            assert (target, source) in declared, (
                f"{source} trunks to {target}, but {target} does not trunk back"
            )


def test_transit_links_have_two_endpoints_inside_their_own_30(inventory):
    """Endpoints drawn from different blocks leave the link up and unusable."""
    for link in inventory["transit_links"]:
        network = ipaddress.ip_network(link["subnet"])
        assert network.prefixlen == 30, f"{link['subnet']} is not a /30"
        assert len(link["endpoints"]) == 2, f"{link['subnet']}: not two endpoints"

        usable = {str(h) for h in network.hosts()}
        assigned = {e["address"] for e in link["endpoints"]}
        assert assigned == usable, (
            f"{link['subnet']} carries {sorted(assigned)}, expected {sorted(usable)}"
        )


def test_the_three_routers_form_a_triangle(inventory):
    """Redundancy depends on the mesh being closed. A chain would leave the
    middle router as a single point of failure."""
    routers = {z["router"]["hostname"] for z in inventory["zones"].values()}
    pairs = {
        frozenset(e["device"] for e in link["endpoints"])
        for link in inventory["transit_links"]
    }
    expected = {frozenset(p) for p in __import__("itertools").combinations(routers, 2)}
    assert pairs == expected, f"mesh is incomplete: {pairs}"


def test_every_router_has_an_ospf_router_id(inventory):
    routers = {z["router"]["hostname"] for z in inventory["zones"].values()}
    configured = set(inventory["ospf"]["router_ids"])
    assert routers == configured, f"missing router-ids: {routers - configured}"


def test_router_ids_are_unique(inventory):
    ids = list(inventory["ospf"]["router_ids"].values())
    duplicates = [i for i, n in Counter(ids).items() if n > 1]
    assert not duplicates, f"router-id assigned twice: {duplicates}"


def test_no_wireless_secrets_are_committed(inventory):
    """Credentials do not belong in a repository."""
    for name, zone in inventory["zones"].items():
        passphrase = zone["wireless"]["passphrase"]
        assert passphrase.startswith("<"), (
            f"{name}: wireless passphrase looks like a real secret"
        )


def test_wireless_uses_wpa2(inventory):
    for name, zone in inventory["zones"].items():
        wireless = zone["wireless"]
        assert wireless["authentication"] == "WPA2-PSK", f"{name}: not WPA2"
        assert wireless["encryption"] == "AES", (
            f"{name}: {wireless['encryption']} rather than AES — "
            "TKIP is deprecated"
        )


def test_port_security_policy_is_coherent(inventory):
    """Policy, not consistency.

    The checks on the rendered output compare against the inventory, so they
    follow it wherever it goes. These constrain what the inventory may say.
    """
    ps = inventory["defaults"]["port_security"]

    assert ps["violation"] in {"protect", "restrict", "shutdown"}, (
        f"unknown violation mode: {ps['violation']}"
    )
    assert ps["learning"] in {"sticky", "static"}, (
        "dynamic learning is lost on reload, leaving the port unprotected "
        "after a power cycle"
    )
    assert 1 <= ps["maximum"] <= 4, (
        f"maximum {ps['maximum']} on a workstation port is high enough that "
        "flooding would succeed before the limit is reached"
    )
    assert ps["ap_maximum"] > ps["maximum"] * 2, (
        f"an access point bridges one MAC per wireless client; a limit of "
        f"{ps['ap_maximum']} against {ps['maximum']} for a workstation is not "
        "a meaningful distinction, and clients would be blocked as they join"
    )
