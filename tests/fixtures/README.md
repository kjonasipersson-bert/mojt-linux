# Upstream kernel configuration fixture

`linux-6.12.107-scripts-config` is an unmodified copy of Linux `scripts/config`
at commit `f717995cb7dcd8998ab15516b8006aea09cfde0d` (tag `v6.12.107`),
from https://github.com/gregkh/linux/blob/f717995cb7dcd8998ab15516b8006aea09cfde0d/scripts/config.
Its upstream SPDX identifier is GPL-2.0. It exercises the actual shell command
dependencies without a network dependency during the regression test.

`linux-6.12.107-lockdown-Kconfig` is the unmodified `security/lockdown/Kconfig`
from the same Linux commit. It records the upstream selector that forces
module signature support when the lockdown LSM and modules are enabled.

`linux-6.12.107-vdso-checkundef.sh` is the unmodified
`arch/x86/entry/vdso/checkundef.sh` from the same Linux commit. The test invokes
it by the vDSO recipe's `sh` command using the declared private PATH.
