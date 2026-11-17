/** Painted PNG art that replaces the built-in SVG (docs/magic-art.md).
 *  Files live in `frontend/public/magic/<key>.png`; the value is the
 *  picture's height / width (cropped to its content), so it can stand on
 *  its cell at the right size. Add a key here when a new file is dropped in. */
const READY: Record<string, number> = {
  "creatures/ash_ghost": 1.013,
  "creatures/ash_wraith": 1.0,
  "creatures/dawn_archer": 1.0,
  "creatures/dawn_griffin": 0.997,
  "creatures/wild_giant": 1.016,
  "creatures/wild_wyvern": 1.003,
  "creatures/lost_victor": 1.502,
  "creatures/lost_widow": 1.176,
  "creatures/lost_bankrupt": 1.006,
  "creatures/lost_bench": 1.818,
  "creatures/lost_father": 2.336,
  "creatures/lost_hook": 1.096,
  "creatures/magic_guard": 1.8,
  "objects/barracks": 1.016,
  "objects/essence_shop": 1.06,
  "objects/infirmary": 0.922,
  "creatures/ash_bones": 1.067,
  "creatures/ash_butcher": 1.019,
  "creatures/ash_dragon": 0.981,
  "creatures/ash_golem": 1.006,
  "creatures/ash_hound": 0.994,
  "creatures/ash_imp": 1.009,
  "creatures/ash_leech": 1.006,
  "creatures/ash_witch": 1.029,
  "creatures/dawn_banner": 1.481,
  "creatures/dawn_guard": 0.988,
  "creatures/dawn_knight": 0.984,
  "creatures/dawn_phoenix": 1.019,
  "creatures/dawn_priest": 1.131,
  "creatures/dawn_sister": 1.168,
  "creatures/dawn_spear": 0.966,
  "creatures/dawn_squire": 1.29,
  "creatures/wild_bouncer": 1.212,
  "creatures/wild_crossbow": 1.029,
  "creatures/wild_crow": 0.969,
  "creatures/wild_harpy": 1.003,
  "creatures/wild_ogre": 1.003,
  "creatures/wild_sling": 1.088,
  "creatures/wild_thug": 1.046,
  "creatures/wild_troll": 1.046,
  "decals/ash_decal_1": 0.411,
  "decals/ash_decal_2": 0.604,
  "decals/ash_decal_3": 0.521,
  "decals/ash_decal_4": 1.548,
  "decals/desert_decal_1": 0.833,
  "decals/desert_decal_2": 0.531,
  "decals/desert_decal_3": 0.656,
  "decals/desert_decal_4": 0.573,
  "decals/meadow_decal_1": 0.521,
  "decals/meadow_decal_2": 0.443,
  "decals/meadow_decal_3": 0.432,
  "decals/meadow_decal_4": 0.875,
  "decals/snow_decal_1": 0.307,
  "decals/snow_decal_2": 0.328,
  "decals/snow_decal_3": 0.656,
  "decals/snow_decal_4": 0.63,
  "objects/artifact_armband": 1.018,
  "objects/artifact_boots": 1.003,
  "objects/artifact_flag": 1.032,
  "objects/artifact_shinguards": 0.972,
  "objects/artifact_whistle": 1.04,
  "objects/camp_1": 0.507,
  "objects/camp_2": 0.943,
  "objects/camp_3": 0.962,
  "objects/camp_ash": 1.01,
  "objects/camp_dawn": 0.99,
  "objects/shrine": 1.042,
  "objects/tunnel": 0.983,
  "objects/medic": 1.0,
  "objects/floodtower": 1.948,
  "objects/training": 0.88,
  "objects/castle_victor": 1.463,
  "objects/camp_4": 0.51,
  "objects/camp_taken": 0.951,
  "objects/castle_ash": 0.941,
  "objects/castle_dawn": 1.091,
  "objects/castle_ice": 1.029,
  "objects/castle_stadium": 0.993,
  "objects/castle_cup": 1.043,
  "objects/castle_volcano": 1.003,
  "objects/chest": 0.965,
  "objects/chest_taken": 0.979,
  "objects/hero_ash": 1.018,
  "objects/hero_ember": 1.269,
  "objects/hero_grove": 1.258,
  "objects/hero_mage_ash": 1.247,
  "objects/hero_mage_dawn": 1.315,
  "objects/hero_night": 1.099,
  "objects/hero_ranger_ash": 1.297,
  "objects/hero_ranger_dawn": 1.385,
  "objects/hero_dawn": 1.025,
  "objects/hero_frost": 1.166,
  "objects/hero_gold": 1.0,
  "objects/hero_shadow": 1.029,
  "objects/market": 0.99,
  "objects/mine": 0.87,
  "objects/reinforce": 0.99,
  "objects/tribune": 0.997,
  "objects/well": 0.979,
  "terrain/ash_ground": 0.5,
  "terrain/ash_mountain": 1.041,
  "terrain/ash_mountain_2": 0.61,
  "terrain/ash_mountain_3": 0.707,
  "terrain/ash_mountain_4": 0.617,
  "terrain/ash_mountain_5": 2.885,
  "terrain/ash_rock": 0.98,
  "terrain/ash_grove": 0.93,
  "terrain/ash_rock_2": 1.008,
  "terrain/ash_rocks": 0.926,
  "terrain/ash_tree_2": 1.058,
  "terrain/ash_tree": 0.93,
  "terrain/desert_ground": 0.5,
  "terrain/desert_mountain": 1.008,
  "terrain/desert_rock": 0.996,
  "terrain/desert_grove": 1.032,
  "terrain/desert_rock_2": 0.613,
  "terrain/desert_rocks": 0.785,
  "terrain/desert_tree_2": 1.225,
  "terrain/desert_tree": 1.041,
  "terrain/meadow_ground": 0.5,
  "terrain/meadow_mountain": 1.012,
  "terrain/meadow_rock": 0.996,
  "terrain/meadow_rock_2": 0.762,
  "terrain/meadow_rocks": 0.691,
  "terrain/meadow_tree": 1.008,
  "terrain/meadow_tree_2": 1.684,
  "terrain/meadow_grove": 0.754,
  "terrain/snow_ground": 0.5,
  "terrain/snow_mountain": 1.041,
  "terrain/snow_rock": 0.977,
  "terrain/snow_grove": 1.016,
  "terrain/snow_rock_2": 0.809,
  "terrain/snow_rocks": 0.797,
  "terrain/snow_tree_2": 1.225,
  "terrain/snow_tree": 0.961,
  "terrain/ash_road_end": 0.5,
  "terrain/ash_road_fork": 0.5,
  "terrain/ash_road_straight": 0.5,
  "terrain/ash_road_turn_bottom": 0.5,
  "terrain/ash_road_turn_side": 0.5,
  "terrain/ash_road_turn_top": 0.5,
  "terrain/desert_road_end": 0.5,
  "terrain/desert_road_fork": 0.5,
  "terrain/desert_road_straight": 0.5,
  "terrain/desert_road_turn_bottom": 0.5,
  "terrain/desert_road_turn_side": 0.5,
  "terrain/desert_road_turn_top": 0.5,
  "terrain/meadow_road_end": 0.5,
  "terrain/meadow_road_fork": 0.5,
  "terrain/meadow_road_straight": 0.5,
  "terrain/meadow_road_turn_bottom": 0.5,
  "terrain/meadow_road_turn_side": 0.5,
  "terrain/meadow_road_turn_top": 0.5,
  "terrain/snow_road_end": 0.5,
  "terrain/snow_road_fork": 0.5,
  "terrain/snow_road_straight": 0.5,
  "terrain/snow_road_turn_bottom": 0.5,
  "terrain/snow_road_turn_side": 0.5,
  "terrain/snow_road_turn_top": 0.5,
};

// Several codes share one picture (the guard of every rarity is the same guardsman).
const ALIAS: Record<string, string> = {
  "creatures/magic_guard_common": "creatures/magic_guard",
  "creatures/magic_guard_epic": "creatures/magic_guard",
  "creatures/magic_guard_legend": "creatures/magic_guard",
};

export function pngArt(key: string): string | null {
  key = ALIAS[key] ?? key;
  // The ratio doubles as a cache key: a redrawn picture gets a new ratio, so browsers fetch it again.
  return key in READY ? `${import.meta.env.BASE_URL}magic/${key}.png?v=${READY[key]}` : null;
}

// Seamless top-down textures (`frontend/public/magic/terrain/<biome>_<ground|water>_tex.webp`),
// laid over the map in the isometric projection. The water of the ash lands is lava.
const TEXTURES = new Set([
  "ash_ground", "ash_water", "desert_ground", "desert_water",
  "meadow_ground", "meadow_water", "snow_ground", "snow_water",
]);

export function texArt(key: string): string | null {
  return TEXTURES.has(key) ? `${import.meta.env.BASE_URL}magic/terrain/${key}_tex.webp` : null;
}

/** Height / width of a registered picture (1 when unknown). */
export function pngRatio(key: string): number {
  return READY[ALIAS[key] ?? key] ?? 1;
}

// Interface art (`frontend/public/magic/ui/<key>.png`): the pack, card backs and frames, icons.
const UI = new Set([
  "magic_pack", "magic_pack_open", "card_back", "card_frame_1", "card_frame_2", "card_frame_3", "card_frame_4",
  "card_frame_5", "class_knight", "class_mage", "class_ranger", "icon_essence", "icon_leadership", "icon_wounded",
  "captain_badge", "guard_banner", "emblem_dawn", "emblem_ash", "emblem_wild", "magic_ball",
]);
// Battle grounds (`frontend/public/magic/battle/<biome>.webp`), one painted field per map biome.
// "lair": the cracked violet pitch of the Lost lairs and of Безликий.
const BATTLE = new Set(["meadow", "snow", "desert", "ash", "lair"]);
export function battleArt(biome: string): string | null {
  return BATTLE.has(biome) ? `${import.meta.env.BASE_URL}magic/battle/${biome}.webp` : null;
}
// Pitch obstacles (`frontend/public/magic/battle/obstacles/<kind>.png`): football junk and each biome's hazard.
const OBSTACLES = new Set(["cones", "dummies", "ball_cart", "goalpost", "bench", "meadow", "snow", "desert", "ash",
  "floodlight", "mirror", "grave"]);
export function obstacleArt(kind: string): string | null {
  return OBSTACLES.has(kind) ? `${import.meta.env.BASE_URL}magic/battle/obstacles/${kind}.png` : null;
}
export function uiArt(key: string): string | null {
  return UI.has(key) ? `${import.meta.env.BASE_URL}magic/ui/${key}.png` : null;
}
