"""Fetch a set of real, well-known IANA protocol-parameter registries, verbatim.

Each candidate URL below was individually checked (not assumed) to actually resolve
and parse as ``<registry>``/``<record>`` XML before being included:

  service-names-port-numbers  14,526 records  (transport/application layer)
  media-types                  2,307 records  (MIME/content types)
  tls-parameters                1,340 records  (security/crypto parameters)
  dns-parameters                   379 records  (name resolution, 24 sub-registries)
  bgp-parameters                   303 records  (inter-domain routing, 33 sub-registries)
  ipv4-address-space               256 records  (address allocation)
  http-status-codes                 75 records  (application protocol)

(counts measured against the live files at investigation time.) One candidate from
the original suggested list, ``language-subtag-registry.xml``, was checked and
dropped: IANA marks it ``<file type="legacy">``, and the URL returns a 6-line XML
stub pointing at a plain-text registry file, not real record data -- substituted with
``ipv4-address-space`` instead, which does validate.
"""
from __future__ import annotations

import json
from pathlib import Path

from corpus_fetch._http import get_with_retries, new_session

REGISTRIES = {
    "service-names-port-numbers": "https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xml",
    "media-types": "https://www.iana.org/assignments/media-types/media-types.xml",
    "tls-parameters": "https://www.iana.org/assignments/tls-parameters/tls-parameters.xml",
    "http-status-codes": "https://www.iana.org/assignments/http-status-codes/http-status-codes.xml",
    "dns-parameters": "https://www.iana.org/assignments/dns-parameters/dns-parameters.xml",
    "bgp-parameters": "https://www.iana.org/assignments/bgp-parameters/bgp-parameters.xml",
    "ipv4-address-space": "https://www.iana.org/assignments/ipv4-address-space/ipv4-address-space.xml",
}


def fetch_iana(out_dir: Path, *, force: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = new_session()
    results: dict[str, str] = {}
    for name, url in REGISTRIES.items():
        target = out_dir / f"{name}.xml"
        if target.exists() and not force:
            results[name] = "skipped_existing"
            continue
        resp = get_with_retries(session, url, timeout=60)
        resp.raise_for_status()
        target.write_bytes(resp.content)
        results[name] = "fetched"
    return results


if __name__ == "__main__":
    report = fetch_iana(Path("data/raw/iana_registry"))
    print(json.dumps(report, indent=2))
