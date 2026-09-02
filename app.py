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

    # The draw can only be reshuffled before the tournament has started,
    # i.e. before any match has a recorded winner.
    tournament_started = any(m.winner_id for m in matches)

    return render_template(
        'bracket.html',
        teams=teams,
        rounds=rounds,
        num_teams=num_teams,
        allowed_sizes=ALLOWED_SIZES,
        final_match=final_match,
        tournament_started=tournament_started
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
    """Version A: randomly re-draws round 1 matchups for an already-generated
    bracket. Blocked once any match has a winner, so an in-progress
    tournament can't be scrambled by mistake.
    """
    matches = Match.query.order_by(Match.round, Match.match_index).all()

    if not matches:
        return redirect(url_for('bracket'))

    if any(m.winner_id for m in matches):
        # Tournament already underway — refuse to touch the draw.
        return redirect(url_for('bracket'))

    round1_matches = [m for m in matches if m.round == 1]
    teams = Bracket.query.order_by(Bracket.seed).all()

    random.shuffle(teams)

    for i, match in enumerate(round1_matches):
        match.team1_id = teams[i * 2].id
        match.team2_id = teams[i * 2 + 1].id

    db.session.commit()
    return redirect(url_for('bracket'))

@app.route("/redraw", methods=["POST"])
def redraw():
    """Version B: full tournament redraw. Unlike /reshuffle, this is allowed
    at ANY stage, including mid-tournament — but it wipes every recorded
    winner and resets every later round back to empty before generating a
    brand new random draw. Requires an explicit confirm=yes field so it
    can't be triggered accidentally.
    """
    if request.form.get("confirm") != "yes":
        return redirect(url_for('bracket'))

    teams = Bracket.query.order_by(Bracket.seed).all()
    if not teams:
        return redirect(url_for('bracket'))

    matches = Match.query.order_by(Match.round, Match.match_index).all()

    random.shuffle(teams)

    round1_matches = [m for m in matches if m.round == 1]
    later_matches = [m for m in matches if m.round > 1]

    for i, match in enumerate(round1_matches):
        match.team1_id = teams[i * 2].id
        match.team2_id = teams[i * 2 + 1].id
        match.winner_id = None

    for match in later_matches:
        match.team1_id = None
        match.team2_id = None
        match.winner_id = None

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