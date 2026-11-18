import debut from "@/assets/prospect/prospect-debut.webp";
import empty from "@/assets/prospect/prospect-empty.webp";
import graduation from "@/assets/prospect/prospect-graduation.webp";
import hall from "@/assets/prospect/prospect-hall.webp";
import icon from "@/assets/prospect/prospect.webp";
import school from "@/assets/prospect/prospect-school.webp";
import u19 from "@/assets/prospect/prospect-u19.webp";
import yard from "@/assets/prospect/prospect-yard.webp";
import youth from "@/assets/prospect/prospect-youth.webp";

/** «Воспитанник Академии» art: a scene per stage (the top half is the
 * scene, the bottom half dark and empty — the avatar and text go there). */
export const STAGE_SCENES: Record<string, string> = { yard, school, youth, u19, debut };
export const PROSPECT_ART = { empty, graduation, hall, icon };

export const stageScene = (code: string | undefined) => STAGE_SCENES[code ?? ""] ?? yard;
