# Signed Artifact and Provenance Verification

## Goal

Verify release artifacts and build provenance before deployment.

## Required Inputs

- release tag
- artifact checksums (`SHA256SUMS`)
- signature bundle (`SHA256SUMS.sig`)
- provenance attestation (SLSA/in-toto style statement)
- trusted public key material (team-managed)

## Verification Steps

1. Fetch release assets for the target tag.
2. Verify checksum signature with trusted release key.
3. Verify each artifact hash against `SHA256SUMS`.
4. Verify provenance attestation signature and subject digest matches artifact digest.
5. Verify attestation source context:
   - repository owner/name
   - workflow identity
   - commit SHA
   - immutable build inputs

## Policy Gates

Deployment must fail if any of the following are true:
- checksum signature invalid
- artifact hash mismatch
- provenance signature invalid
- provenance subject digest mismatch
- provenance repo/workflow context mismatch

## Operational Notes

- Keep release signing key rotation documented and audited.
- Store verification logs with deployment records.
- Re-verify artifacts during incident response rollback drills.
