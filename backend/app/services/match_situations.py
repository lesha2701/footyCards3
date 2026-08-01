from dataclasses import dataclass

from app.models.enums import Position

# Position pools mirror lineup_service.CATEGORY_POSITIONS — kept local (not
# imported) since these tuples are ordered/curated per situation rather than
# a flat category set, and importing would suggest they must stay identical.
_FWD_WIDE = (Position.LW, Position.RW)
_FWD_ANY = (Position.LW, Position.ST, Position.RW)
_MID_CENTRAL = (Position.CDM, Position.CM, Position.CAM)
_MID_ANY = (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM)
_DEF_WIDE = (Position.LB, Position.RB)
_DEF_ANY = (Position.LB, Position.CB, Position.RB)


@dataclass(frozen=True)
class AttackSituation:
    id: str
    shot_type: str  # "in_box" | "long_range"
    shooter_category: str  # "FWD" | "MID"
    shooter_positions: tuple[Position, ...]
    pass_target_category: str
    pass_target_positions: tuple[Position, ...]
    bias: float  # positive favors Shoot, negative favors Pass
    template: str  # "{shooter}", "{pass_target}"


@dataclass(frozen=True)
class DefenseSituation:
    id: str
    shot_type: str  # "in_box" | "long_range"
    defender_category: str  # "DEF" | "MID"
    defender_positions: tuple[Position, ...]
    tags: tuple[str, ...]  # "box" -> a foul here can escalate to a penalty-style continuation
    template: str  # "{defender}", "{them}"


ATTACK_SITUATIONS: list[AttackSituation] = [
    AttackSituation(
        id="att_box_narrow_angle", shot_type="in_box",
        shooter_category="FWD", shooter_positions=_FWD_WIDE,
        pass_target_category="FWD", pass_target_positions=(Position.ST,),
        bias=-7,
        template="{shooter} врывается в штрафную под острым углом. В центре набегает {pass_target} — путь до ворот свободнее.",
    ),
    AttackSituation(
        id="att_box_through_ball", shot_type="in_box",
        shooter_category="FWD", shooter_positions=(Position.ST,),
        pass_target_category="MID", pass_target_positions=(Position.CAM,),
        bias=8,
        template="{shooter} выходит один на один после разрезающего паса! Сбоку без опеки открывается {pass_target}.",
    ),
    AttackSituation(
        id="att_box_cutback", shot_type="in_box",
        shooter_category="FWD", shooter_positions=_FWD_WIDE,
        pass_target_category="FWD", pass_target_positions=_FWD_ANY,
        bias=9,
        template="{shooter} проходит по флангу и оказывается у лицевой линии с мячом. {pass_target} влетает на дальнюю штангу совсем один!",
    ),
    AttackSituation(
        id="att_long_range_edge_box", shot_type="long_range",
        shooter_category="MID", shooter_positions=_MID_CENTRAL,
        pass_target_category="FWD", pass_target_positions=(Position.ST,),
        bias=-6,
        template="{shooter} получает мяч на подступах к штрафной — защита соперника подстроилась. {pass_target} требует мяч внизу.",
    ),
    AttackSituation(
        id="att_long_range_speculative", shot_type="long_range",
        shooter_category="FWD", shooter_positions=(Position.ST,),
        pass_target_category="MID", pass_target_positions=(Position.CM, Position.CDM),
        bias=-8,
        template="{shooter} видит вратаря на линии и задумывается о дальнем ударе — угол непростой. {pass_target} остаётся свободным чуть позади.",
    ),
    AttackSituation(
        id="att_box_one_on_one", shot_type="in_box",
        shooter_category="FWD", shooter_positions=(Position.ST,),
        pass_target_category="FWD", pass_target_positions=_FWD_WIDE,
        bias=10,
        template="Вратарь уже выбежал навстречу — {shooter} один на один! {pass_target} набегает сбоку, но угол там хуже.",
    ),
    AttackSituation(
        id="att_box_crowded", shot_type="in_box",
        shooter_category="FWD", shooter_positions=_FWD_ANY,
        pass_target_category="MID", pass_target_positions=(Position.CAM,),
        bias=-9,
        template="{shooter} зажат между двумя защитниками в штрафной. {pass_target} освобождается чуть дальше, на линии штрафной.",
    ),
    AttackSituation(
        id="att_long_range_deflection", shot_type="long_range",
        shooter_category="MID", shooter_positions=(Position.CDM, Position.CM),
        pass_target_category="FWD", pass_target_positions=(Position.ST,),
        bias=-5,
        template="{shooter} нацеливается на удар со средней дистанции, но перед ним стенка защитников. {pass_target} открывается справа.",
    ),
    AttackSituation(
        id="att_box_far_post", shot_type="in_box",
        shooter_category="FWD", shooter_positions=_FWD_WIDE,
        pass_target_category="FWD", pass_target_positions=(Position.ST,),
        bias=7,
        template="Прострел находит {shooter} на дальней штанге. {pass_target} тоже свободен в центре, но чуть дальше от ворот.",
    ),
    AttackSituation(
        id="att_long_range_counter", shot_type="long_range",
        shooter_category="FWD", shooter_positions=(Position.ST,),
        pass_target_category="FWD", pass_target_positions=_FWD_WIDE,
        bias=6,
        template="После быстрой контратаки {shooter} остаётся один перед защитой — вратарь ещё не занял позицию. {pass_target} чуть отстаёт сбоку.",
    ),
    AttackSituation(
        id="att_box_keeper_advanced", shot_type="in_box",
        shooter_category="FWD", shooter_positions=(Position.ST,),
        pass_target_category="MID", pass_target_positions=(Position.CAM,),
        bias=9,
        template="Вратарь соперника слишком далеко вышел из ворот! {shooter} готов пробить над ним. {pass_target} просит пас низом.",
    ),
    AttackSituation(
        id="att_long_range_open_lane", shot_type="long_range",
        shooter_category="MID", shooter_positions=(Position.CM,),
        pass_target_category="MID", pass_target_positions=(Position.CDM,),
        bias=5,
        template="{shooter} видит свободный коридор для удара с дальней дистанции. {pass_target} закрыт защитником — пас рискован.",
    ),
]

DEFENSE_SITUATIONS: list[DefenseSituation] = [
    DefenseSituation(
        id="def_box_cutback_run", shot_type="in_box",
        defender_category="DEF", defender_positions=(Position.CB,),
        tags=("box",),
        template="Нападающий {them} врывается в штрафную на большой скорости. {defender} — последний, кто может его остановить.",
    ),
    DefenseSituation(
        id="def_winger_run", shot_type="in_box",
        defender_category="DEF", defender_positions=_DEF_WIDE,
        tags=("box",),
        template="Вингер {them} обыгрывает по флангу и уходит на угол вратарской. {defender} спешит на подстраховку.",
    ),
    DefenseSituation(
        id="def_long_range_edge", shot_type="long_range",
        defender_category="DEF", defender_positions=_DEF_ANY,
        tags=(),
        template="Полузащитник {them} нацеливается на дальний удар с линии штрафной. {defender} бросается закрыть удар.",
    ),
    DefenseSituation(
        id="def_through_ball_cover", shot_type="in_box",
        defender_category="MID", defender_positions=(Position.CDM,),
        tags=("box",),
        template="{them} разрезает оборону идеальным пасом — партнёр по атаке выходит один на один. {defender} успевает вернуться и вступить в борьбу.",
    ),
    DefenseSituation(
        id="def_counter_attack", shot_type="long_range",
        defender_category="DEF", defender_positions=(Position.CB,),
        tags=(),
        template="{them} убегает в контратаку по центру поля. {defender} — единственный защитник, оставшийся позади.",
    ),
    DefenseSituation(
        id="def_box_far_post_cross", shot_type="in_box",
        defender_category="DEF", defender_positions=_DEF_ANY,
        tags=("box",),
        template="Прострел летит на дальнюю штангу, туда набегает нападающий {them}. {defender} должен успеть первым.",
    ),
    DefenseSituation(
        id="def_long_range_half_space", shot_type="long_range",
        defender_category="MID", defender_positions=(Position.CM, Position.CDM),
        tags=(),
        template="{them} смещается в полуфланг и готовится пробить издали. {defender} пытается перекрыть траекторию удара.",
    ),
    DefenseSituation(
        id="def_box_one_on_one", shot_type="in_box",
        defender_category="DEF", defender_positions=(Position.CB,),
        tags=("box",),
        template="{them} вырывается один на один с твоим вратарём. {defender} — последняя надежда обороны.",
    ),
    DefenseSituation(
        id="def_box_low_cross", shot_type="in_box",
        defender_category="DEF", defender_positions=_DEF_WIDE,
        tags=("box",),
        template="Низкий прострел проходит через штрафную, {them} готов замкнуть его в касание. {defender} бросается перекрыть передачу.",
    ),
    DefenseSituation(
        id="def_long_range_rebound", shot_type="long_range",
        defender_category="DEF", defender_positions=(Position.CB,),
        tags=(),
        template="Мяч отскакивает на угол штрафной прямо к {them}. {defender} первый в борьбе за подбор.",
    ),
    DefenseSituation(
        id="def_box_corner_scramble", shot_type="in_box",
        defender_category="DEF", defender_positions=(Position.CB,),
        tags=("box",),
        template="После подачи с углового в штрафной начинается свалка, мяч подкатывается к {them}. {defender} рядом и готов вмешаться.",
    ),
    DefenseSituation(
        id="def_winger_cutback_pass", shot_type="in_box",
        defender_category="MID", defender_positions=(Position.LM, Position.RM),
        tags=("box",),
        template="{them} проходит по флангу и готовит навес на дальнюю штангу. {defender} пытается перекрыть подачу в подкате.",
    ),
]

ATTACK_SITUATIONS_BY_SHOT_TYPE: dict[str, list[AttackSituation]] = {
    shot_type: [s for s in ATTACK_SITUATIONS if s.shot_type == shot_type]
    for shot_type in ("in_box", "long_range")
}
DEFENSE_SITUATIONS_BY_SHOT_TYPE: dict[str, list[DefenseSituation]] = {
    shot_type: [s for s in DEFENSE_SITUATIONS if s.shot_type == shot_type]
    for shot_type in ("in_box", "long_range")
}
ATTACK_SITUATIONS_BY_ID: dict[str, AttackSituation] = {s.id: s for s in ATTACK_SITUATIONS}
DEFENSE_SITUATIONS_BY_ID: dict[str, DefenseSituation] = {s.id: s for s in DEFENSE_SITUATIONS}
