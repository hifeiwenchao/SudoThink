"""Comment client addresses and offline, privacy-limited IP locations."""
from __future__ import annotations

import asyncio
from functools import lru_cache
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from pathlib import Path
import struct
from threading import Lock

from app.core.config import settings


def _address(value, *, map_v4=True):
    if not isinstance(value, str) or len(value) > 64 or "%" in value:
        raise ValueError("Invalid IP address")
    result = ip_address(value.strip())
    if map_v4 and isinstance(result, IPv6Address) and result.ipv4_mapped:
        return result.ipv4_mapped
    return result


@lru_cache(maxsize=16)
def _trusted_networks(configuration: str):
    """A malformed or universally trusted configuration must fail closed."""
    try:
        networks = tuple(ip_network(item.strip()) for item in configuration.split(",") if item.strip())
        return () if any(network.prefixlen == 0 for network in networks) else networks
    except (AttributeError, TypeError, ValueError):
        return ()


def get_comment_ip(request) -> str:
    """Return the actual socket peer unless an explicit trusted proxy is used."""
    try:
        peer = _address(request.ip)
    except (AttributeError, TypeError, ValueError):
        return ""
    networks = _trusted_networks(settings.TRUSTED_PROXY_CIDRS)

    def trusted(address):
        return any(address in network for network in networks)

    if not trusted(peer):
        return str(peer)
    # Sanic's request.ip is the socket peer, unlike request.remote_addr. Never
    # use X-Real-IP/Forwarded or let Sanic's proxy defaults select our client.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if not isinstance(forwarded, str) or not forwarded or len(forwarded) > 2048:
        return str(peer)
    hops = forwarded.split(",")
    if len(hops) > 32:
        return str(peer)
    current = peer
    try:
        for value in reversed(hops):
            if not trusted(current):
                break
            current = _address(value)
    except ValueError:
        return str(peer)
    return str(current)


class _QQWry:
    """Bounded reader for the traditional little-endian QQWry IPv4 .dat format.

    Only the country/location field is read. The second field (ISP, street,
    company or other area details) is deliberately never exposed or decoded.
    This reader uses only the standard library, including on Python 3.15.
    """

    MAX_BYTES = 128 * 1024 * 1024

    def __init__(self, path: Path):
        with path.open("rb") as source:
            self.data = source.read(self.MAX_BYTES + 1)
        if len(self.data) < 15 or len(self.data) > self.MAX_BYTES:
            raise ValueError("Invalid QQWry size")
        self.first, last = struct.unpack_from("<II", self.data)
        if self.first < 8 or last < self.first or (last - self.first) % 7 or last + 7 > len(self.data):
            raise ValueError("Invalid QQWry index")
        self.count = (last - self.first) // 7 + 1
        previous_start = previous_end = -1
        for index in range(self.count):
            position = self.first + index * 7
            start = self._number(position, 4)
            record = self._number(position + 4, 3)
            end = self._number(record, 4)
            # Some releases contain nested IANA ranges in the multicast or
            # reserved tail. They are never located publicly; sorted starts
            # still support binary search without rebuilding the index.
            if start <= previous_start or end < start or (start < 0xE0000000 and start <= previous_end):
                raise ValueError("Invalid QQWry ranges")
            previous_start, previous_end = start, end

    def _number(self, position: int, size: int) -> int:
        if position < 8 or position + size > len(self.data):
            raise ValueError("QQWry pointer outside file")
        return int.from_bytes(self.data[position:position + size], "little")

    def _country(self, position: int) -> str:
        visited = set()
        # The format uses 0x01 for record redirection and 0x02 for country-only
        # redirection. Both ultimately point to a NUL-terminated country field.
        for _ in range(16):
            if position in visited or not 8 <= position < len(self.data):
                raise ValueError("Invalid QQWry country pointer")
            visited.add(position)
            if self.data[position] in (1, 2):
                position = self._number(position + 1, 3)
                continue
            end = self.data.find(b"\0", position, min(position + 1024, len(self.data)))
            if end < 0:
                raise ValueError("Unterminated QQWry country")
            return self.data[position:end].decode("gb18030")
        raise ValueError("Too many QQWry redirections")

    def lookup(self, address: IPv4Address) -> str:
        number = int(address)
        lower, upper = 0, self.count
        while lower < upper:
            middle = (lower + upper) // 2
            start = self._number(self.first + middle * 7, 4)
            if start <= number:
                lower = middle + 1
            else:
                upper = middle
        if lower == 0:
            return ""
        index = self.first + (lower - 1) * 7
        record = self._number(index + 4, 3)
        if number > self._number(record, 4):
            return ""
        return self._country(record + 4)


# Administrative names are an allowlist: never send arbitrary database text to
# the public API. Older/unknown names safely fall back to the known province.
_PROVINCES = tuple(sorted((
    "河北省 山西省 辽宁省 吉林省 黑龙江省 江苏省 浙江省 安徽省 福建省 江西省 山东省 "
    "河南省 湖北省 湖南省 广东省 海南省 四川省 贵州省 云南省 陕西省 甘肃省 青海省 台湾省 "
    "内蒙古自治区 内蒙古 广西壮族自治区 广西 宁夏回族自治区 宁夏 新疆维吾尔自治区 新疆 "
    "西藏自治区 西藏"
).split(), key=len, reverse=True))
_MUNICIPALITIES = ("北京市", "上海市", "天津市", "重庆市")
_CITIES = tuple(sorted((
    "石家庄市 唐山市 秦皇岛市 邯郸市 邢台市 保定市 张家口市 承德市 沧州市 廊坊市 衡水市 "
    "太原市 大同市 阳泉市 长治市 晋城市 朔州市 晋中市 运城市 忻州市 临汾市 吕梁市 "
    "呼和浩特市 包头市 乌海市 赤峰市 通辽市 鄂尔多斯市 呼伦贝尔市 巴彦淖尔市 乌兰察布市 兴安盟 锡林郭勒盟 阿拉善盟 "
    "沈阳市 大连市 鞍山市 抚顺市 本溪市 丹东市 锦州市 营口市 阜新市 辽阳市 盘锦市 铁岭市 朝阳市 葫芦岛市 "
    "长春市 吉林市 四平市 辽源市 通化市 白山市 松原市 白城市 延边朝鲜族自治州 "
    "哈尔滨市 齐齐哈尔市 鸡西市 鹤岗市 双鸭山市 大庆市 伊春市 佳木斯市 七台河市 牡丹江市 黑河市 绥化市 大兴安岭地区 "
    "南京市 无锡市 徐州市 常州市 苏州市 南通市 连云港市 淮安市 盐城市 扬州市 镇江市 泰州市 宿迁市 "
    "杭州市 宁波市 温州市 嘉兴市 湖州市 绍兴市 金华市 衢州市 舟山市 台州市 丽水市 "
    "合肥市 芜湖市 蚌埠市 淮南市 马鞍山市 淮北市 铜陵市 安庆市 黄山市 滁州市 阜阳市 宿州市 六安市 亳州市 池州市 宣城市 "
    "福州市 厦门市 莆田市 三明市 泉州市 漳州市 南平市 龙岩市 宁德市 "
    "南昌市 景德镇市 萍乡市 九江市 新余市 鹰潭市 赣州市 吉安市 宜春市 抚州市 上饶市 "
    "济南市 青岛市 淄博市 枣庄市 东营市 烟台市 潍坊市 济宁市 泰安市 威海市 日照市 临沂市 德州市 聊城市 滨州市 菏泽市 莱芜市 "
    "郑州市 开封市 洛阳市 平顶山市 安阳市 鹤壁市 新乡市 焦作市 濮阳市 许昌市 漯河市 三门峡市 南阳市 商丘市 信阳市 周口市 驻马店市 济源市 "
    "武汉市 黄石市 十堰市 宜昌市 襄阳市 鄂州市 荆门市 孝感市 荆州市 黄冈市 咸宁市 随州市 恩施土家族苗族自治州 仙桃市 潜江市 天门市 "
    "长沙市 株洲市 湘潭市 衡阳市 邵阳市 岳阳市 常德市 张家界市 益阳市 郴州市 永州市 怀化市 娄底市 湘西土家族苗族自治州 "
    "广州市 韶关市 深圳市 珠海市 汕头市 佛山市 江门市 湛江市 茂名市 肇庆市 惠州市 梅州市 汕尾市 河源市 阳江市 清远市 东莞市 中山市 潮州市 揭阳市 云浮市 "
    "南宁市 柳州市 桂林市 梧州市 北海市 防城港市 钦州市 贵港市 玉林市 百色市 贺州市 河池市 来宾市 崇左市 "
    "海口市 三亚市 三沙市 儋州市 五指山市 琼海市 文昌市 万宁市 东方市 "
    "成都市 自贡市 攀枝花市 泸州市 德阳市 绵阳市 广元市 遂宁市 内江市 乐山市 南充市 眉山市 宜宾市 广安市 达州市 雅安市 巴中市 资阳市 阿坝藏族羌族自治州 甘孜藏族自治州 凉山彝族自治州 "
    "贵阳市 六盘水市 遵义市 安顺市 毕节市 铜仁市 黔西南布依族苗族自治州 黔东南苗族侗族自治州 黔南布依族苗族自治州 "
    "昆明市 曲靖市 玉溪市 保山市 昭通市 丽江市 普洱市 临沧市 楚雄彝族自治州 红河哈尼族彝族自治州 文山壮族苗族自治州 西双版纳傣族自治州 大理白族自治州 德宏傣族景颇族自治州 怒江傈僳族自治州 迪庆藏族自治州 "
    "拉萨市 日喀则市 昌都市 林芝市 山南市 那曲市 阿里地区 "
    "西安市 铜川市 宝鸡市 咸阳市 渭南市 延安市 汉中市 榆林市 安康市 商洛市 "
    "兰州市 嘉峪关市 金昌市 白银市 天水市 武威市 张掖市 平凉市 酒泉市 庆阳市 定西市 陇南市 临夏回族自治州 甘南藏族自治州 "
    "西宁市 海东市 海北藏族自治州 黄南藏族自治州 海南藏族自治州 果洛藏族自治州 玉树藏族自治州 海西蒙古族藏族自治州 "
    "银川市 石嘴山市 吴忠市 固原市 中卫市 "
    "乌鲁木齐市 克拉玛依市 吐鲁番市 哈密市 昌吉回族自治州 博尔塔拉蒙古自治州 巴音郭楞蒙古自治州 阿克苏地区 克孜勒苏柯尔克孜自治州 喀什地区 和田地区 伊犁哈萨克自治州 塔城地区 阿勒泰地区 石河子市 阿拉尔市 图木舒克市 五家渠市 北屯市 铁门关市 双河市 可克达拉市 昆玉市 胡杨河市 新星市 白杨市 "
    "台北市 新北市 桃园市 台中市 台南市 高雄市 基隆市 新竹市 嘉义市"
).split(), key=len, reverse=True))
_COUNTRIES = tuple(sorted((
    "美国 加拿大 墨西哥 格陵兰 百慕大 圣皮埃尔和密克隆 瓜地马拉 危地马拉 伯利兹 萨尔瓦多 洪都拉斯 尼加拉瓜 哥斯达黎加 巴拿马 "
    "古巴 海地 多米尼加 牙买加 波多黎各 巴哈马 特立尼达和多巴哥 巴巴多斯 格林纳达 圣卢西亚 多米尼克 安提瓜和巴布达 圣基茨和尼维斯 圣文森特和格林纳丁斯 "
    "阿鲁巴 库拉索 荷属圣马丁 英属维尔京群岛 美属维尔京群岛 开曼群岛 特克斯和凯科斯群岛 蒙特塞拉特 安圭拉 "
    "巴西 阿根廷 智利 哥伦比亚 委内瑞拉 秘鲁 厄瓜多尔 玻利维亚 巴拉圭 乌拉圭 圭亚那 苏里南 法属圭亚那 福克兰群岛 "
    "英国 法国 德国 意大利 西班牙 葡萄牙 荷兰 比利时 卢森堡 瑞士 奥地利 爱尔兰 冰岛 挪威 瑞典 芬兰 丹麦 波兰 捷克 斯洛伐克 匈牙利 罗马尼亚 保加利亚 "
    "希腊 塞浦路斯 马耳他 阿尔巴尼亚 塞尔维亚 黑山 波斯尼亚和黑塞哥维那 波黑 克罗地亚 斯洛文尼亚 北马其顿 马其顿 科索沃 安道尔 摩纳哥 圣马力诺 梵蒂冈 列支敦士登 "
    "俄罗斯 乌克兰 白俄罗斯 摩尔多瓦 爱沙尼亚 拉脱维亚 立陶宛 格鲁吉亚 亚美尼亚 阿塞拜疆 直布罗陀 法罗群岛 根西岛 泽西岛 马恩岛 "
    "日本 韩国 朝鲜 蒙古 越南 老挝 柬埔寨 泰国 缅甸 马来西亚 新加坡 印度尼西亚 菲律宾 文莱 东帝汶 印度 巴基斯坦 孟加拉国 尼泊尔 不丹 斯里兰卡 马尔代夫 "
    "哈萨克斯坦 乌兹别克斯坦 土库曼斯坦 吉尔吉斯斯坦 塔吉克斯坦 阿富汗 伊朗 伊拉克 土耳其 沙特阿拉伯 阿联酋 阿拉伯联合酋长国 卡塔尔 巴林 科威特 阿曼 也门 叙利亚 黎巴嫩 约旦 以色列 巴勒斯坦 "
    "埃及 利比亚 突尼斯 阿尔及利亚 摩洛哥 西撒哈拉 苏丹 南苏丹 埃塞俄比亚 厄立特里亚 吉布提 索马里 肯尼亚 乌干达 坦桑尼亚 卢旺达 布隆迪 刚果民主共和国 刚果共和国 刚果 "
    "南非 纳米比亚 博茨瓦纳 津巴布韦 赞比亚 马拉维 莫桑比克 安哥拉 莱索托 斯威士兰 埃斯瓦蒂尼 马达加斯加 科摩罗 毛里求斯 塞舌尔 留尼汪 马约特 "
    "尼日利亚 尼日尔 乍得 中非 喀麦隆 赤道几内亚 加蓬 圣多美和普林西比 贝宁 多哥 加纳 布基纳法索 科特迪瓦 利比里亚 塞拉利昂 几内亚 几内亚比绍 冈比亚 塞内加尔 毛里塔尼亚 马里 佛得角 "
    "澳大利亚 新西兰 巴布亚新几内亚 斐济 所罗门群岛 瓦努阿图 萨摩亚 汤加 图瓦卢 基里巴斯 瑙鲁 帕劳 密克罗尼西亚 马绍尔群岛 库克群岛 纽埃 托克劳 关岛 北马里亚纳群岛 美属萨摩亚 法属波利尼西亚 新喀里多尼亚 瓦利斯和富图纳 诺福克岛"
).split(), key=len, reverse=True))


# Delimited releases omit administrative suffixes. Normalize whole fields
# against the same allowlists, keeping districts and provider text out.
_PROVINCE_ALIASES = {name: name for name in _PROVINCES}
_PROVINCE_ALIASES.update({name[:-1]: name for name in _PROVINCES if name.endswith("省")})
_PROVINCE_ALIASES.update({
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区", "西藏": "西藏自治区",
})
_CITY_ALIASES = {name: name for name in _CITIES}
_CITY_ALIASES.update({name[:-1]: name for name in _CITIES if name.endswith("市")})
_MUNICIPALITY_ALIASES = {alias: name for name in _MUNICIPALITIES for alias in (name, name[:-1])}


def _public_location(raw: str) -> str:
    value = "".join(raw.split())
    if "–" in value:
        parts = value.split("–", 3)
        domestic = parts[0] == "中国"
        if domestic:
            parts = parts[1:]
        region = parts[0]
        for special in ("香港", "澳门"):
            if region in (special, special + "特别行政区"):
                return special
        municipality = _MUNICIPALITY_ALIASES.get(region)
        if municipality:
            return municipality
        province = _PROVINCE_ALIASES.get(region)
        if province:
            city = _CITY_ALIASES.get(parts[1], "") if len(parts) > 1 else ""
            return province + city
        if domestic:
            return "中国"
        for country in _COUNTRIES:
            if region == country:
                return country
        return "未知"
    if value.startswith("中国"):
        value = value[2:]
        domestic = True
    else:
        domestic = False
    for special in ("香港", "澳门"):
        if value.startswith(special):
            return special
    for municipality in _MUNICIPALITIES:
        if value.startswith(municipality):
            return municipality
    for province in _PROVINCES:
        if value.startswith(province):
            remainder = value[len(province):]
            for city in _CITIES:
                if remainder.startswith(city):
                    return province + city
            return province
    if domestic:
        return "中国"
    for country in _COUNTRIES:
        if value.startswith(country):
            return country
    return "未知"


def display_comment_location(location: str | None) -> str:
    """Show the city name while retaining the saved provincial location."""
    value = (location or "").strip()
    value = _CITY_ALIASES.get(value) or _MUNICIPALITY_ALIASES.get(value) or _public_location(value)
    for province in _PROVINCES:
        if value.startswith(province):
            city = value[len(province):]
            if city in _CITIES:
                value = city
            break
    if value in _CITIES or value in _MUNICIPALITIES:
        return value.removesuffix("市")
    return value


_database_lock = Lock()
_database_stamp = None
_database = None


def _locate_sync(address: IPv4Address, configured_path: str) -> str:
    global _database_stamp, _database
    try:
        path = Path(configured_path).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        stat = path.stat()
        stamp = (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns)
        with _database_lock:
            if stamp != _database_stamp:
                _database_stamp, _database = stamp, None
                if 15 <= stat.st_size <= _QQWry.MAX_BYTES:
                    try:
                        _database = _QQWry(path)
                    except (OSError, ValueError, struct.error):
                        pass
            reader = _database
        return _public_location(reader.lookup(address)) if reader is not None else "未知"
    except (OSError, ValueError, TypeError, UnicodeError, struct.error):
        return "未知"


async def locate_comment_ip(ip: str) -> str:
    """Resolve a public location with an optional local QQWry database."""
    try:
        address = _address(ip, map_v4=False)
    except (TypeError, ValueError):
        return "未知"
    # Traditional QQWry does not contain IPv6 data. Never fabricate its result.
    if not isinstance(address, IPv4Address) or not address.is_global or address.is_multicast:
        return "未知"
    if not settings.QQWRY_DB_PATH:
        return "未知"
    return await asyncio.to_thread(_locate_sync, address, settings.QQWRY_DB_PATH)
