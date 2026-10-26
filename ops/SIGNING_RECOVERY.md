# Restoring commit signing in a new environment (F-156)

Signing state is read, never assumed: `python3 ops/signing_audit.py --base <deployed> --head <candidate>`
reports `verified`, `unavailable`, `partial` or `claimed_but_unsigned` from `git log %G? %GK`.
An empty `user.signingkey`, or a key path whose file is missing or empty, means signing is
**unavailable**, not claimed (F-153). Today this environment is `unavailable`: the configured
public key file is empty, every commit reads `%G?=N`, and release records say so.

No private key is ever committed. Only public material and configuration belong in git.

## Steps (owner or operator, on the new machine)

1. Generate a key outside the repository: `ssh-keygen -t ed25519 -f ~/.ssh/brambleloop_signing -C brambleloop-release`.
   The private key stays in `~/.ssh` (or a hardware token / secret manager); never under the repo.
2. Configure git for this clone only:
   `git config gpg.format ssh`,
   `git config user.signingkey ~/.ssh/brambleloop_signing.pub`,
   `git config commit.gpgsign true`.
3. Make signatures independently verifiable: append `"<email> <public key line>"` to an
   allowed-signers file outside the repo and run `git config gpg.ssh.allowedSignersFile <path>`.
   A copy of the public line may be published for reviewers; it is not a secret.
4. Prove it: make a commit and run `git log -1 --format='%G? %GK'` -- it must print `G` and the
   key fingerprint -- then `python3 ops/signing_audit.py --head HEAD` must report
   `"independently_verifiable": true`.
5. Only then set `BRAMBLELOOP_SIGNING_REQUIRED=1` for `ops/deploy_guard.py record`. With it set,
   an unsigned release commit is refused; without it, the release record lists the unsigned
   commit under `signing.unsigned` with `intentional_unsigned: true` (F-157).

A configured key with unsigned commits (`claimed_but_unsigned`) is always refused: a signing
claim that the commits do not support is false evidence.
