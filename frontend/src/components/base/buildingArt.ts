import {
  AccountingArt, AnalyticsArt, type Art, HotelArt, HqArt, MarketingArt, MediaArt, MedicalArt, ShopArt, TrainingArt,
} from "./BaseArt";

/** Building code -> its isometric illustration (BaseArt.tsx). */
export const ART: Record<string, (props: Art) => JSX.Element> = {
  hq: HqArt, hotel: HotelArt, training: TrainingArt, medical: MedicalArt, analytics: AnalyticsArt,
  media: MediaArt, marketing: MarketingArt, shop: ShopArt, accounting: AccountingArt,
};
