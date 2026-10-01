# Private recovery verification before release

The delivery workflow supports two explicit recovery modes. `supabase` remains
the default and requires provider recovery metadata. `signed-local` accepts a
trusted operator's signed evidence that a recent private application database
backup was restored successfully. Failure of one mode never selects the other.

This is a release prerequisite, not an automated disaster recovery service.
CI verifies the signature and release bindings; it does not receive or restore
the archive. The signing key holder is responsible for the accuracy of the
evidence and continued availability of the archive. Losing the workstation or
archive can lose this recovery point. Maintain private backup custody separately
from the public repository and CI artifact storage.

## Scope and prerequisites

The archive covers application tables, data, functions and constraints in the
PostgreSQL `public` schema. It does not back up Supabase managed schemas, provider
settings, roles/ACLs, object storage, Fly volumes or camera image files. Verify
those separately when a release changes them. A database archive contains private
customer records and password hashes; keep it and any restore logs in a directory
restricted to the operator, outside version control. Do not print connection
strings, rows, passwords or keys in shared logs or command arguments.

Use a PostgreSQL dump/restore toolchain compatible with the source server. Obtain
the existing database connection only through an authorized operator procedure;
hold credentials in memory or a protected process environment. Production must
remain read-only throughout backup validation. Never restore into production to
test a backup.

## Produce genuine recovery evidence

1. Record the immutable candidate Git commit, source API release and source
   Alembic revision. Read the Supabase project identity from trusted configuration.
   Resolve the candidate's single Alembic head without connecting it to production.
2. Open a read-only repeatable-read transaction, export its snapshot, and use that
   same snapshot for `pg_dump --format=custom --schema=public --no-owner --no-acl`
   and all application table counts/content fingerprints. Record the snapshot time
   in UTC before the dump. Include a deterministic ordered table inventory and
   schema contracts; a few aggregate business counts are insufficient.
3. Finish the archive, record its byte length and SHA-256, then restore it into a
   new isolated PostgreSQL instance listening only on loopback with restricted
   access. Install required extensions such as `btree_gist`; preserve every
   application object and fail on any restore error. Document any prerequisite
   schema creation or restore-list adjustment; never suppress restore failures.
4. Compare every restored table count/content fingerprint and application schema
   contract with the source snapshot. Check sequences cannot reuse existing IDs.
   Run candidate migrations only on this isolated clone and verify candidate
   schema/deep readiness and data preservation. Retain private proof files and
   their SHA-256. Stop the temporary server after verification.
5. Recheck the archive checksum and every result before signing. A prepared script,
   schema-only export, successful dump without restore, or a test using synthetic
   data is not evidence of production recoverability.

## Sign and configure the gate

Generate an Ed25519 key once in private operator storage with restrictive file
permissions. Never place the private key in the repository, a GitHub secret or an
artifact. Pin its raw 32-byte public key, encoded as standard base64, in the
GitHub `production` environment variable `PARKINGAI_RECOVERY_PUBLIC_KEY`.

`backend/recovery_attestation.py` supplies `sign_attestation(payload, private_key)`
for a trusted local caller. This is only a cryptographic helper: it does not
perform a backup or check the caller's files. The caller must complete the checks
above before invoking it. The strict version-1 payload has these fields:

| Fields | Required meaning |
| --- | --- |
| `version`, `kind` | `1`, `parkingai-local-recovery` |
| `repository`, `fly_app`, `scope` | `lam1826/ParkingAI`, `parkingai-api-lam1826`, `postgres:public` |
| `source_fingerprint` | SHA-256 of `supabase:<project-ref>:postgres:public`; use `source_fingerprint()` |
| `target_sha`, `source_release` | Full 40-character candidate and current source API Git SHAs |
| `source_schema`, `verified_target_schema` | Source revision and candidate Alembic head actually verified on the clone |
| `snapshot_at`, `backup_completed_at`, `restore_verified_at`, `signed_at` | Ordered UTC ISO timestamps; no future timestamps |
| `dump_sha256`, `dump_bytes`, `table_count` | Archive digest and positive byte/table counts |
| `source_tables_sha256`, `restored_tables_sha256` | Equal deterministic aggregate digests of complete table inventory, counts and content fingerprints |
| `restore_proof_sha256` | Digest of retained private restore evidence |
| `checks` | Exactly `archive_restore`, `deep_readiness`, `table_counts`, `fingerprints`, `schema`, `migration`, all literal `true` |

The signed envelope contains exactly `payload` and `signature`; the helper handles
canonical serialization and domain separation. Store the envelope as production
environment secret `PARKINGAI_RECOVERY_ATTESTATION`. Keep the existing
`SUPABASE_PROJECT_REF` secret for independent source-identity binding. Set the
environment variable `PARKINGAI_RECOVERY_MODE` to `signed-local` only after the
valid proof and pinned key are configured. Do not upload the underlying archive.

Run the verifier locally with the same candidate checkout and gate environment
before release. It requires `RELEASE_SHA`, `PUBLIC_API_URL`, the project identity,
public key and envelope. It reads the current release from the pinned HTTPS API
origin and rejects redirects, unknown/missing fields, invalid signatures, stale
snapshots, incorrect source/target/schema and failed checks. Secret values belong
in the process environment, not command-line arguments. At gate time, the snapshot
must be no more than two hours old; signing it again does not reset its age.

## Release, retry and recovery

Publish the exact candidate through normal main-branch CI. Delivery still requires
successful CI and runs the recovery gate before Fly migrations/deployment. A new
commit needs a newly bound proof; an expired snapshot needs a new dump and restore.
If the API source release changes, reassess and obtain evidence for the current
source before retrying. A successful prior deployment cannot silently reuse the
old source binding. Missing or invalid proof stops deployment without a fallback.

After rollout, verify exact release IDs on all service machines, schema/readiness,
frontend/API compatibility and preservation of business state. An application
rollback must remain compatible with the retained schema and authentication
contract. Actual database recovery is a separate, deliberate operation: validate
the private archive and rehearse again before choosing a target; do not blindly
overwrite newer production data. Switching back to `supabase` requires a genuine
provider recovery point that satisfies its existing gate.
