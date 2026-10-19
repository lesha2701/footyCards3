import { IconStar } from "@/components/icons";
import StyleShop from "@/components/shop/StyleShop";

/** «Стиль» page (from the profile): the same catalog as the shop tab. */
export default function StylePage() {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconStar size={20} className="text-amber-300" /> Стиль
      </h1>
      <StyleShop />
    </div>
  );
}
