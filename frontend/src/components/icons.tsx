import {
  IconArrowDownRight, IconArrowUpRight, IconBallAmericanFootball, IconBallBasketball, IconBolt, IconChartBar, IconCloud, IconCloudFog,
  IconCloudRain, IconCloudSnow, IconCloudStorm, IconDeviceDesktop, IconHandGrab, IconHandStop, IconMapPin, IconMedal, IconMoon,
  IconPlus, IconRepeat, IconRocket, IconRun, IconShield, IconSnowflake, IconStarFilled, IconSun, IconSunHigh, IconSunLow,
  IconTarget, IconTemperatureMinus, IconTrophy, IconUsers, IconWall, IconWind, IconFirstAidKit, type Icon,
} from "@tabler/icons-react";
import type { Kind } from "../api";
import type { SkyIcon, WxIcon } from "../format";

// The site's one icon set (Tabler, outline): the same drawing on every device, unlike emoji.

const MARKET: Record<Kind | "all", Icon> = {
  all: IconChartBar, rush: IconRun, rlng: IconWind, rec: IconHandGrab, recs: IconHandStop, lng: IconRocket, pass: IconTarget, ptd: IconTarget,
  rr: IconBolt, td: IconBallAmericanFootball, ftd: IconMedal,
  pts: IconBallBasketball, reb: IconRepeat, ast: IconUsers, threes: IconTarget, pra: IconPlus, pr: IconPlus, pa: IconPlus,
  stl: IconShield, blk: IconWall, dd: IconTrophy, tpl: IconTrophy,
};
const WX: Record<WxIcon, Icon> = { wind: IconWind, snow: IconSnowflake, rain: IconCloudRain, cold: IconTemperatureMinus };
const SKY: Record<SkyIcon, Icon> = { storm: IconCloudStorm, snow: IconCloudSnow, rain: IconCloudRain, fog: IconCloudFog, cloud: IconCloud,
  partly: IconSunLow, moon: IconMoon, sun: IconSunHigh };

const props = (size: number) => ({ size, stroke: 1.75, "aria-hidden": true, className: "icon" });

export const MarketIcon = ({ k, size = 16 }: { k: Kind | "all"; size?: number }) => { const I = MARKET[k]; return <I {...props(size)} />; };
export const WeatherIcon = ({ name, size = 14 }: { name: WxIcon; size?: number }) => { const I = WX[name]; return <I {...props(size)} />; };
export const SkyGlyph = ({ name, size = 40 }: { name: SkyIcon; size?: number }) => { const I = SKY[name]; return <I {...props(size)} />; };
export const LeagueIcon = ({ league, size = 16 }: { league: "nfl" | "nba"; size?: number }) =>
  league === "nba" ? <IconBallBasketball {...props(size)} /> : <IconBallAmericanFootball {...props(size)} />;
/** Over / Under on a pick: which way the line has to go. */
export const SideArrow = ({ side, size = 13 }: { side: "Over" | "Under"; size?: number }) =>
  side === "Over" ? <IconArrowUpRight {...props(size)} /> : <IconArrowDownRight {...props(size)} />;
export const Star = ({ size = 12 }: { size?: number }) => <IconStarFilled size={size} aria-hidden className="icon star" />;
export { IconMapPin as PinIcon, IconSun as SunIcon, IconMoon as MoonIcon, IconDeviceDesktop as SystemIcon, IconFirstAidKit as InjuryIcon };
