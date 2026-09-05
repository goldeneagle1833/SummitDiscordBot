"""Hardcoded fart-roll flavor text. No AI."""

import random

# Flavor copy only — rank wind/poo emojis live on the fart title in FunCog.classify_fart_roll.
FART_FLAVOR_LINES = {
    "ordinary": [
        "A polite puff. The room files it under 'miscellaneous weather.'",
        "That's the sound of a participation trophy evaporating.",
        "Barely a draft. Houseplants didn't even rustle.",
        "You've had more impressive sighs.",
        "Bland. Like leftover steam from someone else's tea.",
        "The universe checked its watch and kept walking.",
        "A whisper of effort. Nobody asked for an encore.",
        "Congrats: you moved air from point A to point A.",
        "Ennui with a soundtrack. The soundtrack is this.",
        "Nature yawned. You were the yawn.",
        "If mediocrity had a mascot, it just waved.",
        "A soft disappointment. Even the curtains stayed loyal.",
        "Groundbreaking? Only if the ground is very, very sleepy.",
        "That's the fart equivalent of a shrug emoji.",
        "Low-stakes breeze. The wind outside is jealous of nothing.",
        "You tried. The air politely declined to notice.",
        "A muted toot. History will not be recording this.",
        "Mild. Forgettable. Already forgotten.",
        "Somewhere, a thunderstorm is laughing at you.",
        "The bare minimum, gift-wrapped in a sigh.",
    ],
    "exceptional": [
        "Hm. That had a little personality. Don't let it go to your head.",
        "A respectable poof. The furniture almost paid attention.",
        "Not boring! Merely... moderately interesting weather.",
        "Okay, that one had a punchline. Short punchline.",
        "A faint spark of showmanship. Keep the day job.",
        "Slightly above leftover steam. The bar was on the floor.",
        "The room tilts one degree toward 'noticed that.'",
        "A modest gust with ambitions. Cute.",
        "There's a melody in there. It's a jingle, not a symphony.",
        "Better than a sigh. Still not a legend.",
        "A tidy little whoosh. We are, against our will, amused.",
        "Mildly spicy air. Like salsa from a packet.",
        "That had some backbone. A small backbone.",
        "The curtains flinched. Progress.",
        "A decent effort — the kind that earns a slow nod.",
        "Not a masterpiece, but it showed up on time.",
        "A warm, unhurried breeze with a hint of attitude.",
        "Somebody's grandmother would say 'well now.' That's the review.",
        "A step up from ordinary. A small, polite step.",
        "The air did a little dance. Two steps, then sat down.",
    ],
    "elite": [
        "That one meant business. The furniture took notes.",
        "A proper gust — smug, confident, a little too proud.",
        "Elite? We'll allow it. The windows briefly considered opening.",
        "That's the sound of competence with a mischievous grin.",
        "A sharp, well-aimed breeze. Someone downwind just learned a lesson.",
        "Rank-and-file air just got outclassed.",
        "Bold. Brassy. The kind of poof that introduces itself.",
        "A thunder-lite rumble. Appetizer for a storm.",
        "That's not background noise. That's a headline in a small town paper.",
        "The room's opinion of you has been forcibly updated.",
        "A stylish blast — part fanfare, part warning shot.",
        "Elite air: fewer words, more impact.",
        "That had swagger. The carpet may never recover its dignity.",
        "A crisp, high-quality whoosh. Vintage, even.",
        "The thermostat just filed a complaint. That's how you know.",
        "Commanding little squall. Junior varsity hurricane.",
        "People will pretend they didn't notice. They noticed.",
        "A gourmet gust. Paired well with stunned silence.",
        "That's the fart equivalent of walking in slow motion.",
        "Solid gold breeze. Not legendary yet — but it's stretching.",
    ],
    "unique": [
        "Impressive. That's a signature stink with a copyright pending.",
        "A one-of-a-kind aromatic event. Scientists would want a sample.",
        "Bravo — that breeze had character, plot, and a twist ending.",
        "Unique? It's practically a calling card. Frame it.",
        "The air just got a personality transplant. Yours.",
        "A true original. Downwind witnesses are writing memoirs.",
        "That's not a fart; that's a limited-edition release.",
        "Wow. Artful, potent, and absolutely unforgettable.",
        "The room will tell this story at parties. Uninvited.",
        "A masterpiece of mischief. The curtains request an autograph.",
        "Rare air. Collectors would fight over the bottle.",
        "That one had range — comedy, drama, and a standing ovation.",
        "Impressed doesn't cover it. The furniture is taking a bow.",
        "A signature gale. Nobody else could have authored this.",
        "The wind outside just asked for your autograph.",
        "That's a legend in training. Keep the receipts.",
        "Aromatic fireworks. No permit. Maximum style.",
        "Unique doesn't do it justice — that's a whole brand.",
        "The kind of blast people fake-remember being there for.",
        "Outstanding. If farts had museums, that's the centerpiece.",
    ],
    "curio_shart": [
        "A CURIO! The heavens briefly considered a parade!",
        "Museum-worthy. Curators are already arguing over the plaque!",
        "Legendary gust! Someone call the wind — it has competition!",
        "This is the good stuff. History just opened a new chapter!",
        "VERY EXCITED. That's a relic. That's a myth. That's YOU!",
        "A once-in-a-season masterpiece — potent, proud, and parading!",
        "Confetti incoming! That curio could knock a hat off a statue!",
        "Nobel-adjacent breeze! The rear department is showing off!",
        "Fanfare! Trumpets! A tiny orchestra just got the memo!",
        "This is peak pageantry. The air itself is taking a victory lap!",
        "A treasured artifact of chaos. Handle with glee!",
        "The room is cheering. The walls are cheering. I'm cheering!",
        "Curio energy: rare, loud, and absolutely delighted with itself!",
        "That's not weather — that's a festival with no permit!",
        "A golden-ticket shart! Frame the moment. Then open a window!",
        "Spectacular! The kind of blast ballads get written about!",
        "We are so back. That curio just rewrote the leaderboard's mood!",
        "Thunderous applause (from the air). Encore is illegal, but tempting!",
        "A crowned classic! Downwind kingdoms just declared a holiday!",
        "Maximum hype. That's a curio, a marvel, a tiny natural disaster of joy!",
    ],
}


def pick_fart_flavor(fart_type):
    """Return a random flavor line for this fart tier."""
    lines = FART_FLAVOR_LINES.get(fart_type) or FART_FLAVOR_LINES["ordinary"]
    return random.choice(lines)


def fart_roll_blurb(fart_message, fart_type, uber_variant=None):
    """Title plus flavor, or empty when an uber-rare variant has its own copy."""
    if uber_variant:
        return ""
    return f"{fart_message} {pick_fart_flavor(fart_type)}"


def compose_fart_body(uber_prefix, variant_effect_msg, mushroom_boost_msg, blurb, points_clause):
    """Assemble the chat body, skipping the default curio line for uber-rares."""
    head = f"{uber_prefix}{variant_effect_msg}{mushroom_boost_msg}"
    if blurb:
        return f"{head}{blurb} {points_clause}"
    return f"{head}{points_clause}"


FARTLORD_PROCLAMATIONS = (
    "I am the Fart Lord! All lesser breezes shall bow, and the air itself pays rent to me! 💨",
    "By decree of the throne of stink: my reign is fragrant, my word is wind, and my court is packed! 💨",
    "Let it be known — I sit atop the leaderboard of fumes, and I did not climb here by accident! 💨",
    "Hear my edict: I am Fart Lord, peak pageantry, a walking weather event, and extremely pleased about it! 💨",
    "I claim this realm of rumble. Bring tribute, open a window, and address me as your Fart Lord! 💨",
)


def pick_fartlord_proclamation():
    """Return a random hardcoded !fartlord proclamation."""
    return random.choice(FARTLORD_PROCLAMATIONS)
