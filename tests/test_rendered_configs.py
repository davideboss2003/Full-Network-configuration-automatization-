"""Checks on the generated configurations.

The inventory tests cover the design; these cover the translation of that
design into IOS. Together they catch both a wrong plan and a wrong renderer.
"""

import re

import pytest

ALL_SWITCH_PORTS = set(range(1, 25))


def commands(text):
    """Configuration lines only.

    Comments are documentation, not behaviour. A check that reads them will
    pass on a device where the command itself was never issued — which is how
    a test becomes worse than no test at all.
    """
    return [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("!")
    ]


STANDALONE = "_hardening"


def devices(rendered):
    """Every generated file except the standalone baseline."""
    return {k: v for k, v in rendered.items() if k != STANDALONE}


def switches(inventory):
    for zone in inventory["zones"].values():
        for switch in zone["switches"]:
            yield zone, switch


def test_one_file_per_device(inventory, rendered):
    expected = {sw["hostname"] for _, sw in switches(inventory)}
    expected |= {f"{z['router']['hostname']}-lan" for z in inventory["zones"].values()}
    expected |= {"_hardening"}      # baseline on its own, for devices outside the inventory
    assert set(rendered) == expected


def test_each_file_sets_its_own_hostname(inventory, rendered):
    for _, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        assert f"hostname {switch['hostname']}" in text


def test_trunk_ports_match_the_inventory(inventory, rendered):
    """A trunk on the wrong port silently isolates whatever is plugged in."""
    for _, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        configured = {
            int(p) for p in re.findall(
                r"interface fastEthernet 0/(\d+)\n description Trunk", text
            )
        }
        declared = {t["port"] for t in switch["trunks"]}
        assert configured == declared, (
            f"{switch['hostname']}: trunks on {sorted(configured)}, "
            f"inventory says {sorted(declared)}"
        )


def test_every_port_is_either_trunk_or_access(inventory, rendered):
    """A port left in the default VLAN is a port an unauthorised device can
    use immediately."""
    for _, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        trunk = {t["port"] for t in switch["trunks"]}

        access = set()
        for first, last in re.findall(
            r"interface range fastEthernet 0/(\d+)-(\d+)", text
        ):
            access |= set(range(int(first), int(last) + 1))
        for single in re.findall(
            r"interface fastEthernet 0/(\d+)\n switchport mode access", text
        ):
            access.add(int(single))

        assert trunk & access == set(), (
            f"{switch['hostname']}: ports {sorted(trunk & access)} are both"
        )
        missing = ALL_SWITCH_PORTS - trunk - access
        assert not missing, f"{switch['hostname']}: ports {sorted(missing)} unconfigured"


def test_access_ports_use_the_user_vlan(inventory, rendered):
    for zone, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        assigned = set(re.findall(r"switchport access vlan (\d+)", text))
        assert assigned == {str(zone["user_vlan"]["id"])}


def test_trunks_carry_only_the_two_vlans_in_use(inventory, rendered):
    """A trunk permits all 4094 VLANs by default, which floods traffic and
    opens a path for VLAN hopping."""
    for zone, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        expected = f"{zone['user_vlan']['id']},{zone['mgmt_vlan']['id']}"
        allowed = set(re.findall(r"switchport trunk allowed vlan (\S+)", text))
        assert allowed == {expected}, f"{switch['hostname']}: allows {allowed}"


def test_each_switch_has_an_svi_and_a_default_gateway(inventory, rendered):
    """Without the gateway a switch answers only inside its own subnet — a
    fault that looks like the request never arrived."""
    for zone, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        assert f"interface vlan {zone['mgmt_vlan']['id']}" in text
        assert f"ip address {switch['mgmt_ip']} {zone['mgmt_vlan']['mask']}" in text
        assert f"ip default-gateway {zone['mgmt_vlan']['gateway']}" in text


def test_spanning_tree_role_is_applied(inventory, rendered):
    for zone, switch in switches(inventory):
        text = rendered[switch["hostname"]]
        vlans = f"{zone['user_vlan']['id']},{zone['mgmt_vlan']['id']}"
        if switch["stp"]:
            assert f"spanning-tree vlan {vlans} root {switch['stp']}" in text
        else:
            assert "spanning-tree vlan" not in text, (
                f"{switch['hostname']} should keep the default priority"
            )


def test_router_sub_interfaces_carry_the_right_tags(inventory, rendered):
    """The sub-interface number is cosmetic; encapsulation dot1Q is what binds
    the interface to a VLAN."""
    for zone in inventory["zones"].values():
        text = rendered[f"{zone['router']['hostname']}-lan"]
        for kind in ("user_vlan", "mgmt_vlan"):
            vlan = zone[kind]
            assert f"encapsulation dot1Q {vlan['id']}" in text
            assert f"ip address {vlan['gateway']} {vlan['mask']}" in text


def test_the_physical_interface_carries_no_address(inventory, rendered):
    for zone in inventory["zones"].values():
        text = rendered[f"{zone['router']['hostname']}-lan"]
        block = text.split(f"interface {zone['router']['lan_interface']}\n")[1]
        block = block.split("exit")[0]
        assert "no ip address" in block


def test_dhcp_excludes_the_reserved_range(inventory, rendered):
    """Without the exclusion, allocation starts at the gateway's own address."""
    reserved = inventory["defaults"]["dhcp_reserved_upto"]
    for zone in inventory["zones"].values():
        text = rendered[f"{zone['router']['hostname']}-lan"]
        prefix = zone["user_vlan"]["subnet"].rsplit(".", 1)[0]
        assert (
            f"ip dhcp excluded-address {prefix}.1 {prefix}.{reserved}" in text
        )


def test_dhcp_advertises_gateway_and_name_server(inventory, rendered):
    for zone in inventory["zones"].values():
        text = rendered[f"{zone['router']['hostname']}-lan"]
        assert f"default-router {zone['user_vlan']['gateway']}" in text
        assert f"dns-server {inventory['defaults']['dns_server']}" in text


def test_the_management_vlan_is_not_served_by_dhcp(inventory, rendered):
    """Infrastructure keeps static addresses; a switch must not lose its
    management address to an expired lease."""
    for zone in inventory["zones"].values():
        text = rendered[f"{zone['router']['hostname']}-lan"]
        pools = re.findall(r"network (\S+) ", text)
        assert zone["mgmt_vlan"]["subnet"] not in pools


def test_committed_configs_carry_placeholders_not_credentials(rendered):
    """configs/ is committed, so every credential in it must be a placeholder.

    Real values live in automation/secrets.yml, which is git-ignored, and reach
    only build/ when rendering with --deploy.
    """
    credential = re.compile(r"\b(?:secret|password)\s+(\S+)")
    for hostname, text in rendered.items():
        for value in credential.findall(text):
            assert value.startswith("<"), (
                f"{hostname}: '{value}' looks like a real credential "
                f"in a committed file"
            )


def test_every_device_requires_a_privileged_password(rendered):
    """Without `enable secret`, anyone reaching the console owns the device."""
    for hostname, text in rendered.items():
        issued = [l for l in commands(text) if l.startswith("enable secret ")]
        assert issued, f"{hostname}: no enable secret"


def test_passwords_are_hashed_not_stored_in_clear(rendered):
    """`secret` hashes; `password` stores reversibly. Never the second."""
    for hostname, text in rendered.items():
        weak = re.findall(r"^username \S+ privilege \d+ password ", text, re.M)
        assert not weak, f"{hostname}: account stored with a reversible password"
        assert "service password-encryption" in commands(text), (
            f"{hostname}: remaining plaintext not obscured"
        )


def test_two_privilege_levels_are_defined(rendered):
    """One account to inspect, one to change — not a single account for both."""
    for hostname, text in rendered.items():
        levels = {int(p) for p in re.findall(r"^username \S+ privilege (\d+)", text, re.M)}
        assert len(levels) >= 2, f"{hostname}: only privilege {levels}"
        assert 15 in levels, f"{hostname}: no administrative account"


def test_remote_access_is_ssh_only(rendered):
    """Telnet carries credentials in clear text across the network."""
    for hostname, text in rendered.items():
        lines = commands(text)
        assert "transport input ssh" in lines, f"{hostname}: vty not restricted"
        assert not [l for l in lines if "telnet" in l.lower()], (
            f"{hostname}: telnet permitted"
        )
        assert "ip ssh version 2" in lines, f"{hostname}: SSH v1 still accepted"


def test_ssh_prerequisites_precede_key_generation(rendered):
    """RSA key generation fails unless a domain name is already set."""
    for hostname, text in rendered.items():
        lines = commands(text)
        domain = next(i for i, l in enumerate(lines) if l.startswith("ip domain-name"))
        keygen = next(i for i, l in enumerate(lines) if l.startswith("crypto key generate"))
        assert domain < keygen, f"{hostname}: key generated before domain name"


def test_sessions_time_out(rendered):
    """An unattended session left open is an authenticated session anyone
    can walk up to."""
    for hostname, text in rendered.items():
        timeouts = re.findall(r"exec-timeout (\d+) 0", text)
        assert timeouts, f"{hostname}: no idle timeout"
        assert all(0 < int(t) <= 15 for t in timeouts), (
            f"{hostname}: timeout {timeouts} is absent or too long"
        )


def test_console_requires_authentication_too(rendered):
    """Restricting vty while leaving the console open protects nothing from
    anyone with physical access."""
    for hostname, text in rendered.items():
        console = text.split("line console 0")[1].split("exit")[0]
        assert "login local" in console, f"{hostname}: console unauthenticated"


def test_a_banner_is_presented(rendered):
    for hostname, text in rendered.items():
        assert any(l.startswith("banner motd") for l in commands(text)), (
            f"{hostname}: no login banner"
        )
