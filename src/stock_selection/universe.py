"""BIST 100 evreninin config dosyasından okunması ve doğrulanması.

Evren kod içine gömülmez; ``config/bist100_symbols.csv`` sözleşmesi:

```text
symbol,name,sector,effective_from,effective_to,source
```

``effective_to`` boşsa üyelik hâlen geçerlidir. Sektör bilgisi boş
olabilir; bu durumda sahte bir sektör atanmaz, uyarı üretilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd

UNIVERSE_COLUMNS = ["symbol", "name", "sector", "effective_from", "effective_to", "source"]
EXPECTED_UNIVERSE_SIZE = 100


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    name: str
    sector: str | None
    effective_from: date | None
    effective_to: date | None
    source: str


@dataclass(frozen=True)
class Universe:
    members: tuple[UniverseMember, ...]
    as_of: date
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def symbols(self) -> list[str]:
        return [member.symbol for member in self.members]

    @property
    def is_complete(self) -> bool:
        return len(self.members) == EXPECTED_UNIVERSE_SIZE

    @property
    def sector_map(self) -> dict[str, str | None]:
        return {member.symbol: member.sector for member in self.members}

    @property
    def name_map(self) -> dict[str, str]:
        return {member.symbol: member.name for member in self.members}

    @property
    def sources(self) -> list[str]:
        return sorted({member.source for member in self.members if member.source})

    @property
    def effective_from(self) -> date | None:
        dates = [m.effective_from for m in self.members if m.effective_from is not None]
        return max(dates) if dates else None


def _parse_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    return pd.Timestamp(text).date()


def parse_universe_frame(frame: pd.DataFrame, as_of: date | None = None) -> Universe:
    """Bir DataFrame'i doğrulayıp ``as_of`` tarihinde geçerli evrene çevirir."""
    missing = [column for column in UNIVERSE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Evren dosyasında zorunlu sütunlar eksik: {', '.join(missing)}")

    as_of = as_of or date.today()
    working = frame.loc[:, UNIVERSE_COLUMNS].copy()
    working["symbol"] = working["symbol"].astype("string").str.strip().str.upper()
    working["name"] = working["name"].astype("string").str.strip()
    working["sector"] = working["sector"].astype("string").str.strip()
    working["source"] = working["source"].astype("string").str.strip()

    warnings: list[str] = []
    members: list[UniverseMember] = []
    seen: set[str] = set()
    for _, row in working.iterrows():
        symbol = str(row["symbol"]) if not pd.isna(row["symbol"]) else ""
        if not symbol:
            warnings.append("Boş sembol satırı atlandı.")
            continue
        if not symbol.endswith(".IS"):
            warnings.append(f"{symbol}: Yahoo sembolü '.IS' uzantılı olmalı; satır atlandı.")
            continue
        effective_from = _parse_date(row["effective_from"])
        effective_to = _parse_date(row["effective_to"])
        if effective_from is not None and effective_from > as_of:
            continue
        if effective_to is not None and effective_to < as_of:
            continue
        if symbol in seen:
            warnings.append(f"{symbol}: yinelenen sembol; ilk kayıt kullanıldı.")
            continue
        seen.add(symbol)
        sector = None if pd.isna(row["sector"]) or not str(row["sector"]) else str(row["sector"])
        members.append(
            UniverseMember(
                symbol=symbol,
                name=str(row["name"]) if not pd.isna(row["name"]) else symbol,
                sector=sector,
                effective_from=effective_from,
                effective_to=effective_to,
                source=str(row["source"]) if not pd.isna(row["source"]) else "",
            )
        )

    if len(members) != EXPECTED_UNIVERSE_SIZE:
        warnings.append(
            f"universe incomplete: {len(members)} sembol bulundu, {EXPECTED_UNIVERSE_SIZE} bekleniyordu."
        )
    missing_sector = [m.symbol for m in members if not m.sector]
    if missing_sector:
        warnings.append(
            f"{len(missing_sector)} sembolde sektör bilgisi yok; sektör yoğunlaşması kısmi gösterilir."
        )
    return Universe(members=tuple(members), as_of=as_of, warnings=tuple(warnings))


def load_universe(path: str | Path, as_of: date | None = None) -> Universe:
    """CSV dosyasından evreni okur."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Evren dosyası bulunamadı: {csv_path}")
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8")
    return parse_universe_frame(frame, as_of=as_of)


def parse_universe_csv_text(text: str, as_of: date | None = None) -> Universe:
    """Kullanıcının yüklediği CSV metnini doğrular (dosyaya yazmaz)."""
    frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    return parse_universe_frame(frame, as_of=as_of)


def save_universe_csv_text(text: str, path: str | Path) -> Universe:
    """Doğrulanan CSV metnini config dosyasına yazar ve evreni döndürür."""
    universe = parse_universe_csv_text(text)
    if not universe.members:
        raise ValueError("Yüklenen evren dosyasında geçerli sembol yok; dosya yazılmadı.")
    Path(path).write_text(text, encoding="utf-8")
    return universe
