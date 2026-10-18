# Controlled Amazon Bedrock Smoke Test

**Do not run the invocation command in this document until the account owner
has separately authorized one paid request and completed the checklist.** No
live AWS request was made while preparing this procedure.

## What the repository currently configures

- Backend: `bedrock-runtime.converse` through boto3.
- Default model ID: `amazon.nova-lite-v1:0`; `BEDROCK_MODEL_ID` may instead
  select a model identifier or inference profile confirmed for the account.
- Region: must be explicit through `BEDROCK_REGION`, `AWS_REGION`, or
  `AWS_DEFAULT_REGION` when selecting Bedrock. There is no region default in
  Jarvis.
- App request limits: serialized prompt at most 24,000 UTF-8 bytes, response
  text at most 8,192 UTF-8 bytes, and `maxTokens=160`.
- Client timeouts: 5 seconds to connect and 30 seconds to read. One logical
  request makes at most two Converse calls: the initial call and one jittered
  retry for throttling or service-unavailable outcomes. Authentication,
  authorization, invalid-request, configuration, network, and timeout failures
  are not retried by the adapter. No SDK retry is enabled beyond one SDK
  attempt per adapter attempt.
- Bedrock does not return confidence in this adapter. The engine therefore
  escalates to the existing local mock fallback once. A successful smoke test
  proves the provider request/response path only; the final routing decision
  is from the local fallback, not model accuracy.
- With `--record-trace`, JSONL traces distinguish each Bedrock provider attempt
  from the final decision. They omit question, context, credentials, and raw
  provider messages. `request_attempted=true` means the SDK `converse` method
  was called; it does not prove that AWS received or billed the request.

## AWS facts checked for this procedure

AWS documentation currently lists `amazon.nova-lite-v1:0` as a Bedrock Runtime
model ID and documents Nova Lite use with Converse. The Nova Lite model page
currently lists a 300K-token context window and up to 10K output tokens. The
Jarvis limits above are intentionally much lower. AWS also documents
cross-region inference profile IDs (including `us.amazon.nova-lite-v1:0`) and
explains that profile routing depends on source region and can span destination
regions. These general facts do **not** verify this account's model access,
quotas, region enablement, organization policies, IAM policy, or an inference
profile's availability.

Prices depend on the model, region, and actual token usage. No price estimate is
recorded here. Review current regional rates before authorization. A retry may
make a second model invocation and can increase charges; an ambiguous network
failure may occur after the service has processed a request.

## Preflight checklist — do not skip

- [ ] Account owner confirms which AWS account and billing owner will be used,
  that the account is active/verified, and that spending alerts/monitoring are
  in place.
- [ ] An authorized operator selects one AWS region and confirms it is enabled
  for the account and appropriate for the request's data residency rules.
- [ ] Confirm `amazon.nova-lite-v1:0` is currently available for on-demand
  invocation in that region, or choose the appropriate supported inference
  profile ID and confirm its source and destination regions. Recheck AWS's
  current model pages at test time.
- [ ] Confirm any account-specific model access or first-use requirements in
  the Bedrock console. Do not infer access from a model appearing in public
  documentation.
- [ ] An administrator reviews least-privilege authorization for Converse
  (`bedrock:InvokeModel` on the intended inference target). For an inference
  profile, review access to the profile and underlying model resources in all
  possible destination regions. Do not grant broad Bedrock or IAM permissions
  just for this test.
- [ ] Confirm the current [Nova Lite model page](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html),
  [Converse API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html),
  [model/inference-profile regional support](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html),
  [inference prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-prereq.html),
  and [current Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).
- [ ] Review the exact demo request (question, context, and three routing
  options). Do not put personal, confidential, regulated, or production data in
  it. The request contents are sent to Bedrock.
- [ ] Confirm the effective model ID, region, request limits, timeout, retry
  behavior, local trace path, and a maximum of one application invocation. The
  adapter can issue up to two provider calls for one invocation.
- [ ] Confirm which log/trace files will be retained and who can read them.
  The trace is allowlisted, but ordinary process, SDK, shell, or surrounding
  infrastructure logs are outside this trace policy.
- [ ] Decide how the account owner will reconcile the single invocation using
  available AWS billing, CloudTrail, or Bedrock invocation monitoring. A local
  trace records application calls only; it cannot prove that AWS received or
  billed a request, and account monitoring may be delayed or configured
  separately.
- [ ] Obtain explicit authorization for the single invocation after reviewing
  the possible cost and the retry behavior.

## Dry configuration check

This check does not call AWS or create a boto3 client. It only verifies the
local paid-use and region configuration:

```bash
COST_MODE=production ALLOW_PAID=true BEDROCK_REGION=YOUR_VERIFIED_REGION \
  ./.venv/bin/jarvis-decider --backend bedrock
```

Do not use a placeholder region for the paid invocation. A successful readiness
message is not proof of credentials, IAM permissions, model access, regional
availability, or billing state.

## Manually authorized one-request procedure — do not run during Phase 3

Only after the checklist and separate authorization are complete, set the
verified values in the local shell (never paste credentials into chat):

```bash
export COST_MODE=production
export ALLOW_PAID=true
export BEDROCK_REGION=YOUR_VERIFIED_REGION
export BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
./.venv/bin/jarvis-decider --run-demo --backend bedrock --record-trace \
  --trace-path ./traces/phase3-bedrock-smoke.jsonl
```

This command performs an actual billable Bedrock inference and can issue at most
one retry for a throttling or service-unavailable response. Do not place it in
a loop or rerun it automatically. Check the CLI exit status and trace outcome;
do not treat a configuration-ready message as a successful invocation. The
trace can be inspected locally, but it contains no full response and is not a
provider billing record.

After the one authorized run, remove the paid opt-in from the shell and return
to free mode:

```bash
unset COST_MODE ALLOW_PAID BEDROCK_REGION BEDROCK_MODEL_ID
```

Do not share credentials, raw SDK exception payloads, or complete prompts in
issue reports. For a failed test, use the sanitized `provider_outcome`, model
identifier, selected region, UTC time, and AWS request ID only if it is
available from an approved secure diagnostic path.

## Evidence and limitations

Confirmed from repository code/tests: model ID default, Converse payload shape,
response validation, app-level byte/token caps, client timeout/retry settings,
error classifications, free-by-default provider-selection guard, and trace
fields. Confirmed from public AWS documentation: the model identifier and
Converse usage pattern described above. Not verified: this account's AWS
identity, billing status, region and profile access, IAM authorization, quota,
model-access state, or successful live invocation.
