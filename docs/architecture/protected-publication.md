# Protected publication inputs (P3-T10)

Placement preview routes resolve the working CEM/PDM on the server. They accept
only positions of the exact saved component inventory. Device dimensions,
catalog/model versions, local terminal anchors, rail affiliation, enclosure and
hardware geometry, thermal inputs and validation policy come from the verified
saved snapshots. Exact catalog pins must remain available. Foreign identities,
duplicate components and unsupported rotations are rejected. Responses are draft
previews (`persisted: false`); neither validation nor rerouting publishes them.
Use shared operations to commit a movement, then explicitly Recompute and accept.

`GET /api/projects/{id}/validation/working` returns the aggregate for the current
working snapshots plus a SHA-256 `report_signature` over the document identity,
sequence, engineering content hash and canonical report. This digest binds review
to exact content; it is not an authentication signature or human approval.

`POST /api/projects/{id}/design/publish` accepts:

```json
{
  "document_id": "<working document UUID>",
  "expected_document_sequence": 1,
  "expected_version": 2,
  "report_signature": "<64 lowercase hex characters>"
}
```

The service requires matching project/document clocks, clean accepted snapshots,
a matching report, and valid attached stage results for the current input plan.
It replays the complete stage plan using verified cache entries only. A cache
miss never executes engineering, substitutes another result or changes the working
document. Signature/content/assets are verified, and replayed snapshots and pins
must equal the accepted document. Missing full-plan evidence (including evidence
for retained manual outputs) blocks publication conservatively; incremental
Recompute alone is not a promise that all publication evidence exists.

Required FAIL/UNRESOLVED and engineering ineligibility block publication. The
current snapshot adapter retains unresolved C01–C09 engineering obligations;
therefore existing prototype reports cannot authorize publication. This task
adds no engineering approval provider and supplies no human signature. Draft Save
remains independent and permits unresolved input. Legacy `/design/generate` and
the revision-creation route using that service now reject with
`GENERATION_PROPOSAL_REQUIRED`, including empty-document bootstrap publication.
Server generation proposals remain available without publication.

Artifact preparation occurs after detached verification. The existing atomic
revision writer fences both project lock and document sequence/content, so any
failure leaves the previous revision intact. Captured stage metadata is also
rechecked under the project lock before publication, fencing status-only changes
from concurrent workers. Historical restore, import and
compatibility conversion retain their separate existing contracts.

Origin/session authorization remains the separate P3-T12 responsibility. Existing
CORS restrictions do not supply mutation authentication. No new session approval
or authentication mechanism is claimed here. DB engineering and geometry remain
prototype assumptions, without manufacturing or standards certification.
