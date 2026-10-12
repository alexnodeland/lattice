# Service principals and keys

A service principal is a tenant's non-human member: an integration, a CI job, an MCP client with no person behind it. It is granted roles like a person, and acts with a key.

## Its id

A service principal's id is a `PrincipalId`: not empty, and with no `:`, `~` or whitespace. The libraries' own actors take ids with a `:`, such as relayr's rules (`reflexr:<rule>`), so no principal a tenant makes, and no key it issues, can pass for one ([ADR-0028](../adr/0028-a-principals-id-cant-pass-for-the-libraries-actors.md)). An id outside that form is refused wherever a principal is made, and the admin API answers it with 422.

## Issuing a key

```python
from grantr import Resource, ServicePrincipal, User

ALICE = User(id="alice")
ci = ServicePrincipal(id="ci")

await grants.add_member("acme", ci, by=ALICE)
await grants.grant("acme", "viewer", on=Resource(kind="workspace", workspace="main"), to=ci, by=ALICE)
key, entry = await grants.issue_key("acme", ci, by=ALICE)
```

A key is `grantr_sk_<id>_<secret>`, shown once: grantr stores its public id, its tenant, its principal and a digest of its secret, never the secret. Issuing or revoking one needs `grantr:issue_key` or `grantr:revoke_key`, and every action the principal's grants hold, since a key acts with them. `revoke_key` takes the key's id, and removing the principal takes its keys with it.

## Answering a key

```python
found = await grants.authenticate(key)  # ("acme", ServicePrincipal(id="ci")), or None
```

`authenticate` finds the key by its id and compares digests in constant time. It answers with the key's one tenant and its principal, so a key reaches only its own tenant; give that tenant to the admin API's `Caller(principal, tenant)`, and to the libraries' resolvers. A key for the application's own principal is never answered.

stackr's template takes a key in the `Authorization` header only, where a token would be, so it never lands in a URL's logs, and checks the libraries' external agents with no person behind them as the key's principal.
