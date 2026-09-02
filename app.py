import math
import random
from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bracket.db'
db = SQLAlchemy(app)

ALLOWED_SIZES = [4, 8, 16]

class Bracket(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    seed = db.Column(db.Integer, nullable=False)

class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer, nullable=False)
    match_index = db.Column(db.Integer, nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    team2_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    team1 = db.relationship('Bracket', foreign_keys=[team1_id])
    team2 = db.relationship('Bracket', foreign_keys=[team2_id])
    winner = db.relationship('Bracket', foreign_keys=[winner_id])

def round_label(round_num, total_rounds, num_teams):
    """Returns a human-readable label for a given round number."""
    if round_num == total_rounds:
        return "Final"
    if round_num == total_rounds - 1:
        return "Semifinals"
    if round_num == total_rounds - 2:
        return "Quarterfinals"
    participants = num_teams // (2 ** (round_num - 1))
    return f"Round of {participants}"

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/bracket")
def bracket():
    teams = Bracket.query.all()
    matches = Match.query.order_by(Match.round, Match.match_index).all()

    num_teams = len(teams)
    total_rounds = int(math.log2(num_teams)) if num_teams >= 2 else 0

    rounds = []
    for r in range(1, total_rounds + 1):
        rounds.append({
            "number": r,
            "label": round_label(r, total_rounds, num_teams),
            "matches": [m for m in matches if m.round == r]
        })

    final_match = matches[-1] if matches and matches[-1].round == total_rounds else None

    # Teams currently sitting in an undecided match (no winner yet) —
    # these are the only teams eligible to be manually swapped.
    pending_teams = []
    for m in matches:
        if m.winner_id is None:
            if m.team1_id:
                pending_teams.append(m.team1)
            if m.team2_id:
                pending_teams.append(m.team2)

    # A round is only shuffle-eligible if EVERY match in it is fully filled
    # (both teams known) AND none of them have been played yet. This is
    # different from "pending" above — a round with even one recorded
    # result is off-limits for shuffling.
    reshuffle_round = None
    for r in range(1, total_rounds + 1):
        round_matches = [m for m in matches if m.round == r]
        if not round_matches:
            continue
        fully_filled = all(m.team1_id and m.team2_id for m in round_matches)
        untouched = all(m.winner_id is None for m in round_matches)
        if fully_filled and untouched:
            reshuffle_round = r
            break

    return render_template(
        'bracket.html',
        teams=teams,
        rounds=rounds,
        num_teams=num_teams,
        allowed_sizes=ALLOWED_SIZES,
        final_match=final_match,
        pending_teams=pending_teams,
        reshuffle_round=reshuffle_round
    )

@app.route("/setup", methods=["POST"])
def setup():
    team_count = int(request.form.get("team_count", 8))
    if team_count not in ALLOWED_SIZES:
        team_count = 8

    Match.query.delete()
    Bracket.query.delete()

    for i in range(1, team_count + 1):
        name = request.form.get(f"team{i}", f"Team {i}")
        team = Bracket(name=name, seed=i)
        db.session.add(team)

    db.session.commit()

    teams = Bracket.query.order_by(Bracket.seed).all()
    total_rounds = int(math.log2(team_count))

    # Round 1 matches are filled with the actual teams.
    first_round_matches = team_count // 2
    for i in range(first_round_matches):
        match = Match(
            round=1,
            match_index=i,
            team1_id=teams[i * 2].id,
            team2_id=teams[i * 2 + 1].id
        )
        db.session.add(match)

    # Every later round starts empty and fills in as winners advance.
    for r in range(2, total_rounds + 1):
        matches_in_round = team_count // (2 ** r)
        for i in range(matches_in_round):
            match = Match(
                round=r,
                match_index=i,
                team1_id=None,
                team2_id=None
            )
            db.session.add(match)

    db.session.commit()
    return redirect(url_for('bracket'))

@app.route("/reshuffle", methods=["POST"])
def reshuffle():
    """Randomly re-draws one round's matchups — but ONLY a round that is
    completely untouched: every match in it must have both teams already
    known, and none of those matches can have a recorded winner yet.

    This works at any point in the tournament (not just before it starts),
    but it will never touch a round where even one match has already been
    played, and it will never touch a round that isn't fully set up yet
    (e.g. later rounds still waiting on earlier winners).
    """
    matches = Match.query.order_by(Match.round, Match.match_index).all()
    if not matches:
        return redirect(url_for('bracket'))

    total_rounds = max(m.round for m in matches)

    target_round = None
    for r in range(1, total_rounds + 1):
        round_matches = [m for m in matches if m.round == r]
        if not round_matches:
            continue
        fully_filled = all(m.team1_id and m.team2_id for m in round_matches)
        untouched = all(m.winner_id is None for m in round_matches)
        if fully_filled and untouched:
            target_round = r
            break

    if target_round is None:
        # No round is currently eligible — nothing to do.
        return redirect(url_for('bracket'))

    round_matches = [m for m in matches if m.round == target_round]
    team_ids = []
    for m in round_matches:
        team_ids.append(m.team1_id)
        team_ids.append(m.team2_id)

    random.shuffle(team_ids)

    for i, m in enumerate(round_matches):
        m.team1_id = team_ids[i * 2]
        m.team2_id = team_ids[i * 2 + 1]

    db.session.commit()
    return redirect(url_for('bracket'))

@app.route("/swap_teams", methods=["POST"])
def swap_teams():
    """Manually swaps two teams so each faces the other's current opponent.

    Both teams must currently be sitting in an undecided match (no winner
    yet). Already-played matches are never affected.
    """
    try:
        team_a_id = int(request.form.get("team_a"))
        team_b_id = int(request.form.get("team_b"))
    except (TypeError, ValueError):
        return redirect(url_for('bracket'))

    if team_a_id == team_b_id:
        return redirect(url_for('bracket'))

    pending_matches = Match.query.filter(Match.winner_id.is_(None)).all()

    match_a = next((m for m in pending_matches if team_a_id in (m.team1_id, m.team2_id)), None)
    match_b = next((m for m in pending_matches if team_b_id in (m.team1_id, m.team2_id)), None)

    if not match_a or not match_b or match_a.id == match_b.id:
        # One of the teams isn't currently waiting on a match, or
        # they're already scheduled to play each other.
        return redirect(url_for('bracket'))

    if match_a.team1_id == team_a_id:
        match_a.team1_id = team_b_id
    else:
        match_a.team2_id = team_b_id

    if match_b.team1_id == team_b_id:
        match_b.team1_id = team_a_id
    else:
        match_b.team2_id = team_a_id

    db.session.commit()
    return redirect(url_for('bracket'))

@app.route("/declare_winner/<int:match_id>/<int:winner_id>", methods=["POST"])
def declare_winner(match_id, winner_id):
    match = Match.query.get_or_404(match_id)

    if winner_id not in (match.team1_id, match.team2_id):
        return redirect(url_for('bracket'))

    match.winner_id = winner_id
    db.session.commit()

    advance_winner(match)

    return redirect(url_for('bracket'))

def advance_winner(match):
    """Pushes the winner of `match` into the correct slot of the next round."""
    next_round = match.round + 1
    next_match_index = match.match_index // 2

    next_match = Match.query.filter_by(
        round=next_round,
        match_index=next_match_index
    ).first()

    if next_match is None:
        return  

    if match.match_index % 2 == 0:
        next_match.team1_id = match.winner_id
    else:
        next_match.team2_id = match.winner_id

    db.session.commit()

@app.route("/rules")
def rules():
    return render_template('rules.html')

@app.route("/badminton")
def badminton():
    return render_template('badminton.html')

@app.route("/football")
def football():
    return render_template('football.html')

if __name__ == "__main__":
    app.run(debug=True)

with app.app_context():
    db.create_all()