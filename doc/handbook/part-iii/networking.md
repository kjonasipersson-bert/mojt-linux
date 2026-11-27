<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 9. Network configuration

After booting from the installed disk, log in as root at the local console.
The standard installed System starts NetworkManager at boot. Configure it
with `nmcli`. Connections saved from the installed system persist under
`/etc/NetworkManager/system-connections/`. Configure Wi-Fi again on the
installed system if you joined a network from the live USB.

Start by checking which interfaces NetworkManager sees.

```sh
nmcli device status
```

Use the names in the `DEVICE` column wherever the examples refer to an
interface.

System supplies a trust bundle for p11-kit, which provides certificate trust
to the Nixpkgs Firefox build. During boot, System links the running generation's
bundle at `/etc/ssl/trust-source/ca-bundle.trust.p11-kit` if that path is missing.
Existing local trust files are preserved.

## 9.1. Ethernet with DHCP

Plug in an Ethernet cable. On a network with DHCP, NetworkManager normally
connects automatically and obtains an address, a default route and DNS
servers. If the interface shows as disconnected, try activating it manually.
Replace `ETH_IFACE` with the Ethernet interface from `nmcli device status`.

```sh
nmcli device connect ETH_IFACE
```

## 9.2. Join a Wi-Fi network

If `nmcli radio wifi` reports that Wi-Fi is disabled, run `nmcli radio wifi on`.
For a Wi-Fi network with DHCP and a shared passphrase, replace `WIFI_IFACE`
with the Wi-Fi interface and `YOUR_SSID` with the network name. Keep the quotes
around names containing spaces.

```sh
nmcli device wifi list ifname WIFI_IFACE
nmcli --ask device wifi connect 'YOUR_SSID' ifname WIFI_IFACE
```

`--ask` prompts for the Wi-Fi passphrase if needed, keeping it out of the
shell command line. NetworkManager saves the connection profile for reuse.
Run `nmcli connection show` to see saved profiles. If a profile should
connect automatically at boot, set the following option using that profile's
name in place of `PROFILE`.

```sh
nmcli connection modify 'PROFILE' connection.autoconnect yes
```

## 9.3. Set a static IPv4 address for Ethernet

Use the local console because reactivating a profile can interrupt a remote
session. List the profiles with `nmcli connection show` and use the name of
the Ethernet profile in place of `PROFILE`. If one does not exist, create it
first with `nmcli connection add type ethernet ifname ETH_IFACE con-name 'PROFILE'`.

Replace the example address and prefix, gateway and DNS server with the
values for your network.

```sh
nmcli connection modify 'PROFILE' ipv4.method manual \
  ipv4.addresses 192.0.2.10/24 ipv4.gateway 192.0.2.1 ipv4.dns 192.0.2.1
nmcli connection up 'PROFILE'
```

NetworkManager writes DNS settings to `/etc/resolv.conf` using the active
profiles. Set DNS servers on the connection profile to keep the settings
across reconnects.

## 9.4. Check the connection

```sh
nmcli connection show --active
ip -brief address
ip route show default
ip -6 route show default
```

Check that the intended interface has an address. For access outside the
local network, check for a default route for the IP version in use. The
following commands test name resolution and HTTPS on a network with Internet
access.

```sh
getent hosts cache.nixos.org
curl --fail --show-error --silent --max-time 15 https://cache.nixos.org/nix-cache-info
```

For connection failures, inspect the service and its log.

```sh
systemctl status --no-pager NetworkManager.service
journalctl -b -u NetworkManager.service
```

If the interface is missing from `ip -brief link`, check
[device detection and firmware](hardware.md#82-device-detection). For Wi-Fi
association failures, also check `journalctl -b -u wpa_supplicant.service`.

Once the connection works, see [Remote administration with SSH](ssh.md)
to enable remote login. For more profile and device options, see the
[NetworkManager nmcli reference](https://networkmanager.dev/docs/api/latest/nmcli.html).
