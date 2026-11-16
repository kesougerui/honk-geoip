#!/usr/bin/env python3
"""Build a v2ray-format geoip.dat from a base dat plus custom CIDR sets.

Base entries are kept byte-for-byte; custom sets from sets/*.txt are appended as
extra codes (file stem uppercased). A code that already exists in the base is
replaced.

Output is deterministic: same inputs -> same bytes.
"""
import argparse, hashlib, ipaddress, pathlib, sys, urllib.request

def varint(buf, i):
    v = shift = 0
    while True:
        b = buf[i]; i += 1
        v |= (b & 0x7f) << shift; shift += 7
        if not b & 0x80:
            return v, i

def enc_varint(v):
    out = bytearray()
    while True:
        b = v & 0x7f; v >>= 7
        out.append(b | 0x80 if v else b)
        if not v:
            return bytes(out)

def tag(field, wt):
    return enc_varint((field << 3) | wt)

def ld(field, payload):
    return tag(field, 2) + enc_varint(len(payload)) + payload

def split_entries(data):
    """Return [(code, raw_entry_chunk)] preserving base bytes."""
    out, i = [], 0
    while i < len(data):
        key, i = varint(data, i)
        field, wt = key >> 3, key & 7
        if field != 1 or wt != 2:
            raise SystemExit("unexpected top-level field %d wt %d" % (field, wt))
        n, i = varint(data, i)
        body = data[i:i + n]; i += n
        code, j = None, 0
        while j < len(body):
            k, j = varint(body, j)
            f, w = k >> 3, k & 7
            if w != 2:
                raise SystemExit("unexpected entry field wt %d" % w)
            m, j = varint(body, j)
            val = body[j:j + m]; j += m
            if f == 1:
                code = val.decode("utf-8")
        if code is None:
            raise SystemExit("entry without country_code")
        out.append((code, ld(1, body)))
    return out

def build_entry(code, cidrs):
    body = ld(1, code.encode())
    for c in cidrs:
        net = ipaddress.ip_network(c)
        cidr = ld(1, net.network_address.packed) + tag(2, 0) + enc_varint(net.prefixlen)
        body += ld(2, cidr)
    return ld(1, body)

def read_set(path):
    cidrs = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            cidrs.append(str(ipaddress.ip_network(line)))
    return cidrs

def count_cidrs(chunk):
    """Count field-2 (cidr) sub-messages inside one raw entry chunk."""
    n, i = varint(chunk, 1)          # skip tag, read length
    body = chunk[i:i + n]
    count, j = 0, 0
    while j < len(body):
        k, j = varint(body, j)
        f, w = k >> 3, k & 7
        if w != 2:
            raise SystemExit("unexpected entry field wt %d" % w)
        m, j = varint(body, j)
        j += m
        if f == 2:
            count += 1
    return count

def load_base(src):
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=60) as r:
            return r.read()
    return pathlib.Path(src).read_bytes()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="base geoip.dat path or http(s) URL")
    ap.add_argument("--sets", default="sets", help="directory of *.txt CIDR sets")
    ap.add_argument("--out", default="dist/geoip.dat")
    args = ap.parse_args()

    base = load_base(args.base)
    entries = split_entries(base)
    codes = {code for code, _ in entries}

    setdir = pathlib.Path(args.sets)
    customs = []
    for f in sorted(setdir.glob("*.txt")):
        code = f.stem.upper()
        cidrs = read_set(f)
        if not cidrs:
            print("skip empty set:", f); continue
        customs.append((code, cidrs))

    for code, cidrs in customs:
        chunk = build_entry(code, cidrs)
        if code in codes:
            entries = [(c, chunk if c == code else raw) for c, raw in entries]
        else:
            entries.append((code, chunk))

    data = b"".join(raw for _, raw in entries)

    # verify output parses back and every custom code carries the expected cidr count
    got = {c: count_cidrs(raw) for c, raw in split_entries(data)}
    for code, cidrs in customs:
        assert code in got, "missing code %s" % code
        assert got[code] == len(cidrs), "cidr count mismatch for %s: %d != %d" % (
            code, got[code], len(cidrs))

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (out.parent / (out.name + ".sha256sum")).write_text("%s  %s\n" % (digest, out.name))

    print("base entries:", len(entries) - len(customs))
    for code, cidrs in customs:
        print("  + %-10s %d cidrs" % (code, len(cidrs)))
    print("size:", len(data), "sha256:", digest)

if __name__ == "__main__":
    main()
