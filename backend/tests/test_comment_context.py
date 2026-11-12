"""Trusted comment peers and offline, city-limited QQWry locations."""
import importlib
import importlib.util
import ipaddress
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def database(rows, mode=0):
    """Synthetic QQWry data; no licensed third-party IP data is included."""
    data = bytearray(struct.pack("<II", 8, 8 + (len(rows) - 1) * 7) + b"\0" * (7 * len(rows)))
    for index, (first, last, country) in enumerate(rows):
        offset = len(data)
        data[8 + index * 7:15 + index * 7] = (
            struct.pack("<I", int(ipaddress.IPv4Address(first))) + offset.to_bytes(3, "little")
        )
        encoded = country.encode("gb18030") + b"\0"
        area = b"Private ISP and street address\0"
        data += struct.pack("<I", int(ipaddress.IPv4Address(last)))
        if mode == 1:
            target = len(data) + 4
            data += b"\1" + target.to_bytes(3, "little") + encoded + area
        elif mode == 2:
            target = len(data) + 4 + len(area)
            data += b"\2" + target.to_bytes(3, "little") + area + encoded
        elif mode == 3:
            target = len(data) + 4
            country_target = target + 4 + len(area)
            data += b"\1" + target.to_bytes(3, "little")
            data += b"\2" + country_target.to_bytes(3, "little") + area + encoded
        else:
            data += encoded + area
    return bytes(data)


class CommentContextTests(unittest.IsolatedAsyncioTestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("app.core.comment_context"))
        return importlib.import_module("app.core.comment_context")

    def test_direct_peer_ignores_untrusted_headers(self):
        context = self.module()
        request = SimpleNamespace(ip="8.8.8.8", headers={"X-Forwarded-For": "1.1.1.1"})
        with patch.object(context.settings, "TRUSTED_PROXY_CIDRS", ""):
            self.assertEqual(context.get_comment_ip(request), "8.8.8.8")

    async def test_missing_database_keeps_comment_location_unknown(self):
        context = self.module()
        with patch.object(context.settings, "QQWRY_DB_PATH", "/not-present/qqwry.dat"):
            self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "未知")

    def test_only_explicitly_trusted_peers_may_supply_forwarded_chain(self):
        context = self.module()
        cases = (
            ("8.8.8.8", "1.1.1.1", "8.8.8.8"),
            ("10.10.0.2", "8.8.8.8", "8.8.8.8"),
            ("10.10.0.2", "9.9.9.9, 8.8.8.8, 10.10.0.3", "8.8.8.8"),
            ("10.10.0.2", "9.9.9.9, 10.10.0.3", "9.9.9.9"),
            ("10.10.0.2", "8.8.8.8, forged:1234", "10.10.0.2"),
            ("10.10.0.2", "8.8.8.8,", "10.10.0.2"),
            ("10.10.0.2", "", "10.10.0.2"),
            ("::ffff:10.10.0.2", "::ffff:8.8.8.8", "8.8.8.8"),
            ("fd00::2", "2001:4860:4860::8888, fd00::3", "2001:4860:4860::8888"),
        )
        with patch.object(context.settings, "TRUSTED_PROXY_CIDRS", "10.10.0.0/24,fd00::/64"):
            for peer, chain, expected in cases:
                with self.subTest(peer=peer, chain=chain):
                    request = SimpleNamespace(ip=peer, headers={"X-Forwarded-For": chain})
                    self.assertEqual(context.get_comment_ip(request), expected)

    def test_invalid_trust_config_and_unparseable_peer_fail_closed(self):
        context = self.module()
        for config in ("garbage", "0.0.0.0/0", "::/0", "10.10.0.0/24,broken"):
            with patch.object(context.settings, "TRUSTED_PROXY_CIDRS", config):
                request = SimpleNamespace(ip="10.10.0.2", headers={"X-Forwarded-For": "8.8.8.8"})
                self.assertEqual(context.get_comment_ip(request), "10.10.0.2")
        for peer in (None, "unknown", "8.8.8.8:1234", "fe80::1%eth0"):
            self.assertEqual(context.get_comment_ip(SimpleNamespace(ip=peer, headers={})), "")

    async def test_all_qqwry_country_storage_modes_only_expose_city(self):
        context = self.module()
        with tempfile.TemporaryDirectory() as directory:
            for mode in range(4):
                path = Path(directory) / f"mode-{mode}.dat"
                path.write_bytes(database([("8.8.8.0", "8.8.8.255", "广东省深圳市南山区")], mode))
                with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                    self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "广东省深圳市")

    async def test_detailed_location_retains_district_in_all_country_storage_modes(self):
        context = self.module()
        with tempfile.TemporaryDirectory() as directory:
            for mode in range(4):
                with self.subTest(mode=mode):
                    path = Path(directory) / f"detailed-{mode}.dat"
                    path.write_bytes(database([
                        ("8.8.8.0", "8.8.8.255", "广东省深圳市南山区"),
                    ], mode))
                    with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                        self.assertEqual(await context.locate_comment_ip_detail("8.8.8.8"), "广东省深圳市南山区")
                        self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "广东省深圳市")

    async def test_detailed_location_falls_back_for_missing_corrupt_or_disabled_database(self):
        context = self.module()
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.dat"
            corrupt = Path(directory) / "corrupt.dat"
            corrupt.write_bytes(b"broken database")
            for path in (str(missing), str(corrupt), ""):
                with self.subTest(path=path), patch.object(context.settings, "QQWRY_DB_PATH", path):
                    self.assertEqual(await context.locate_comment_ip_detail("8.8.8.8"), "未知")

    async def test_detailed_location_rejects_private_ipv6_and_invalid_addresses_without_lookup(self):
        context = self.module()
        for address in ("10.0.0.1", "127.0.0.1", "::1", "2001:4860:4860::8888", "::ffff:8.8.8.8", "bad", "", None):
            with self.subTest(address=address), patch.object(context, "_lookup_sync", side_effect=AssertionError("unexpected database access")):
                self.assertEqual(await context.locate_comment_ip_detail(address), "未知")

    async def test_domestic_shapes_and_foreign_countries_never_leak_district_or_isp(self):
        context = self.module()
        cases = (
            ("中国 浙江省 杭州市 西湖区 电信", "浙江省杭州市"),
            ("广东省深圳市南山区", "广东省深圳市"),
            ("北京市海淀区中关村", "北京市"),
            ("上海市浦东新区", "上海市"),
            ("中国香港特别行政区九龙城区", "香港"),
            ("香港", "香港"), ("澳门特别行政区", "澳门"),
            ("台湾省台北市信义区", "台湾省台北市"),
            ("内蒙古呼和浩特市新城区", "内蒙古呼和浩特市"),
            ("广西壮族自治区南宁市电信", "广西壮族自治区南宁市"),
            ("新疆维吾尔自治区伊犁哈萨克自治州电信", "新疆维吾尔自治区伊犁哈萨克自治州"),
            ("广东省电信", "广东省"), ("中国移动", "中国"),
            ("美国加利福尼亚州洛杉矶AT&T", "美国"),
            ("日本东京", "日本"), ("新加坡Cloud Provider", "新加坡"),
            ("英国伦敦", "英国"), ("加拿大安大略省", "加拿大"),
            ("CZ88.NET", "未知"), ("未知", "未知"), ("IANA保留地址", "未知"),
            ("电信数据中心", "未知"), ("上海市8.8.8.8 ISP", "上海市"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (raw, expected) in enumerate(cases):
                with self.subTest(raw=raw):
                    path = Path(directory) / f"location-{index}.dat"
                    path.write_bytes(database([("8.8.8.0", "8.8.8.255", raw)]))
                    with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                        self.assertEqual(await context.locate_comment_ip("8.8.8.8"), expected)

    async def test_qqwry_search_obeys_range_boundaries_and_gaps(self):
        context = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ranges.dat"
            path.write_bytes(database([
                ("1.0.0.0", "1.0.0.10", "日本东京"),
                ("8.8.8.0", "8.8.8.255", "广东省深圳市"),
                ("9.9.9.0", "9.9.9.255", "美国纽约州"),
            ]))
            cases = (("1.0.0.0", "日本"), ("1.0.0.10", "日本"), ("1.0.0.11", "未知"),
                     ("8.8.8.0", "广东省深圳市"), ("8.8.8.255", "广东省深圳市"),
                     ("9.9.9.255", "美国"), ("9.9.10.0", "未知"))
            with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                for ip, expected in cases:
                    with self.subTest(ip=ip):
                        self.assertEqual(await context.locate_comment_ip(ip), expected)

    async def test_delimited_qqwry_locations_normalize_only_allowlisted_province_and_city(self):
        context = self.module()
        cases = (
            ("中国–江苏–南京", "江苏省南京市"),
            ("中国–浙江–杭州–西湖区–电信", "浙江省杭州市"),
            ("中国–广东省–深圳市–南山区", "广东省深圳市"),
            ("江苏–南京", "江苏省南京市"),
            ("中国–江苏", "江苏省"),
            ("中国–江苏–未收录城市–南京", "江苏省"),
            ("中国–江苏–电信数据中心–南京", "江苏省"),
            ("中国–未收录省–南京", "中国"),
            ("中国–北京–北京–海淀区", "北京市"),
            ("中国–上海市–浦东新区", "上海市"),
            ("中国–内蒙古–呼和浩特–新城区", "内蒙古自治区呼和浩特市"),
            ("中国–广西–南宁", "广西壮族自治区南宁市"),
            ("中国–香港–九龙", "香港"),
            ("中国–澳门–花地玛堂区", "澳门"),
            ("中国–台湾–台北–信义区", "台湾省台北市"),
            ("美国–加利福尼亚州–圣克拉拉–山景城", "美国"),
            ("未收录国家–江苏–南京", "未知"),
            ("中国–江苏–南京机房", "江苏省"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (raw, expected) in enumerate(cases):
                with self.subTest(raw=raw):
                    path = Path(directory) / f"delimited-{index}.dat"
                    path.write_bytes(database([("8.8.8.0", "8.8.8.255", raw)]))
                    with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                        self.assertEqual(await context.locate_comment_ip("8.8.8.8"), expected)

    async def test_overlapping_reserved_tail_does_not_disable_public_locations(self):
        context = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reserved-tail.dat"
            path.write_bytes(database([
                ("8.8.8.0", "8.8.8.255", "日本"),
                ("224.0.0.0", "239.255.255.255", "IANA"),
                ("225.0.0.0", "225.255.255.255", "IANA"),
                ("249.0.0.0", "254.255.255.255", "IANA"),
                ("250.0.0.0", "250.255.255.255", "IANA"),
                ("251.0.0.0", "251.255.255.255", "IANA"),
            ]))
            with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "日本")
                self.assertEqual(await context.locate_comment_ip("250.0.0.1"), "未知")

    def test_reserved_tail_still_rejects_reversed_duplicate_and_out_of_bounds_indexes(self):
        context = self.module()
        cases = (
            [("250.0.0.0", "250.255.255.255", "IANA"),
             ("249.0.0.0", "254.255.255.255", "IANA")],
            [("250.0.0.0", "250.255.255.255", "IANA"),
             ("250.0.0.0", "251.255.255.255", "IANA")],
            [("250.0.0.0", "249.255.255.255", "IANA")],
        )
        contents = [database(rows) for rows in cases]
        pointer = bytearray(database([("250.0.0.0", "250.255.255.255", "IANA")]))
        pointer[12:15] = (len(pointer) + 4).to_bytes(3, "little")
        contents.append(bytes(pointer))
        with tempfile.TemporaryDirectory() as directory:
            for index, content in enumerate(contents):
                with self.subTest(index=index):
                    path = Path(directory) / f"invalid-tail-{index}.dat"
                    path.write_bytes(content)
                    with self.assertRaises(ValueError):
                        context._QQWry(path)

    async def test_nonpublic_and_ipv6_addresses_are_unknown_without_database_access(self):
        context = self.module()
        for ip in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1", "169.254.1.1", "0.0.0.0",
                   "100.64.0.1", "224.0.0.1", "255.255.255.255", "::1", "fd00::1", "fe80::1",
                   "2001:4860:4860::8888", "::ffff:8.8.8.8", "203.0.113.1", "bad", "", None):
            with self.subTest(ip=ip), patch.object(context, "_locate_sync", side_effect=AssertionError("unexpected database access")):
                self.assertEqual(await context.locate_comment_ip(ip), "未知")

    async def test_relative_database_path_is_independent_of_working_directory(self):
        context = self.module()
        backend = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=backend) as directory:
            path = Path(directory) / "relative.dat"
            path.write_bytes(database([("8.8.8.0", "8.8.8.255", "日本")]))
            with patch.object(context.settings, "QQWRY_DB_PATH", str(path.relative_to(backend))):
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "日本")

    async def test_reversed_range_and_overlapping_unsorted_indexes_are_rejected(self):
        context = self.module()
        cases = (
            [("8.8.8.0", "8.8.7.255", "日本")],
            [("9.9.9.0", "9.9.9.255", "日本"), ("8.8.8.0", "8.8.8.255", "美国")],
            [("8.8.8.0", "8.8.8.200", "日本"), ("8.8.8.100", "8.8.8.255", "美国")],
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, rows in enumerate(cases):
                path = Path(directory) / f"invalid-range-{index}.dat"
                path.write_bytes(database(rows))
                with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                    self.assertEqual(await context.locate_comment_ip("8.8.8.120"), "未知")

    async def test_missing_or_corrupt_database_recovers_after_atomic_replacement(self):
        context = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qqwry.dat"
            with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "未知")
                path.write_bytes(b"broken database")
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "未知")
                replacement = path.with_suffix(".new")
                replacement.write_bytes(database([("8.8.8.0", "8.8.8.255", "日本东京")]))
                replacement.replace(path)
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "日本")
                replacement.write_bytes(database([("8.8.8.0", "8.8.8.255", "美国纽约")]))
                replacement.replace(path)
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "美国")

    async def test_bad_country_pointers_unterminated_strings_and_loop_do_not_escape(self):
        context = self.module()
        valid = bytearray(database([("8.8.8.0", "8.8.8.255", "日本")], mode=2))
        record = int.from_bytes(valid[12:15], "little")
        broken = []
        loop = valid.copy()
        loop[record + 5:record + 8] = (record + 4).to_bytes(3, "little")
        broken.append(loop)
        beyond = valid.copy()
        beyond[record + 5:record + 8] = (len(valid) + 10).to_bytes(3, "little")
        broken.append(beyond)
        broken.append(valid[:-1])
        broken.append(struct.pack("<II", 8, 0xFFFFFF) + valid[8:])
        with tempfile.TemporaryDirectory() as directory:
            for index, contents in enumerate(broken):
                path = Path(directory) / f"bad-{index}.dat"
                path.write_bytes(contents)
                with patch.object(context.settings, "QQWRY_DB_PATH", str(path)):
                    self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "未知")

    async def test_database_io_and_lookup_run_outside_the_event_loop(self):
        context = self.module()
        main_thread = threading.get_ident()
        identifiers = []
        original = Path.open

        def record_open(path, *args, **kwargs):
            identifiers.append(threading.get_ident())
            return original(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "thread.dat"
            path.write_bytes(database([("8.8.8.0", "8.8.8.255", "日本")]))
            with patch.object(context.settings, "QQWRY_DB_PATH", str(path)), patch.object(Path, "open", record_open):
                self.assertEqual(await context.locate_comment_ip("8.8.8.8"), "日本")
        self.assertTrue(identifiers)
        self.assertNotIn(main_thread, identifiers)
