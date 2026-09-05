import math
import random
import string

from flask import Flask, flash, redirect, render_template, request, url_for
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
    access_code = db.Column(db.String(6), nullable=True)

class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(6), nullable=False)
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

def generate_access_code():
    """Generate a random 6-character access code like ABC123"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_all_tournaments():
    all_teams = Bracket.query.order_by(Bracket.access_code, Bracket.seed).all()

    codes_in_order = []
    teams_by_code = {}
    for teams in all_teams:
        if teams.access_code not in codes_in_order:
            codes_in_order.append(teams.access_code)
            teams_by_code[teams.access_code] = []
        teams_by_code[teams.access_code].append(teams)

    tournaments = []
    for code in codes_in_order:
        teams = teams_by_code[code]
        matches = Match.query.filter_by(access_code=code).order_by(Match.round, Match.match_index).all()

        num_teams = len(teams)
        total_rounds = int(math.log2(num_teams)) if num_teams >= 2 else 0

        rounds = []
        for r in range(1, total_rounds + 1):
            rounds.append({
                "number": r,
                "label": round_label(r, total_rounds, num_teams),
                "matches": [m for m in matches if m.round == r]
            })

        final_match = next((m for m in matches if m.round == total_rounds and m.winner_id), None)   

        tournaments.append({
            "code": code,
            "num_teams": num_teams,
            "teams": teams,
            "rounds": rounds,
            "final_match": final_match,
            "is_complete": final_match is not None
        })

    tournaments.reverse()
    return tournaments

def get_bracket_context(code):
    """Fetch a code's teams/matches and compute shared derived data
    (rounds, pending teams, shuffle-eligible round) used by both the
    creator view and the spectator/join view.
    """
    code = code.upper()
    teams = Bracket.query.filter_by(access_code=code).all()

    if not teams:
        return None

    matches = Match.query.filter_by(access_code=code).order_by(Match.round, Match.match_index).all()

    num_teams = len(teams)
    total_rounds = int(math.log2(num_teams)) if num_teams >= 2 else 0

    rounds = []
    for r in range(1, total_rounds + 1):
        rounds.append({
            "number": r,
            "label": round_label(r, total_rounds, num_teams),
            "matches": [m for m in matches if m.round == r]
        })

    final_match = next((m for m in matches if m.round == total_rounds and m.winner_id), None)

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
    # (both teams known) AND none of them have been played yet.
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

    return {
        "code": code,
        "teams": teams,
        "matches": matches,
        "num_teams": num_teams,
        "total_rounds": total_rounds,
        "rounds": rounds,
        "final_match": final_match,
        "pending_teams": pending_teams,
        "reshuffle_round": reshuffle_round,
    }

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/bracket")
def bracket():
    # No code yet — this just shows the setup form to create a new bracket.
    return render_template(
        'bracket.html',
        teams=[],
        rounds=[],
        num_teams=0,
        allowed_sizes=ALLOWED_SIZES,
        final_match=None,
        pending_teams=[],
        reshuffle_round=None,
        code = None,
        is_creator=False,
        tournaments=get_all_tournaments()
    )

@app.route("/setup", methods=["POST"])
def setup():
    access_code = generate_access_code()

    team_count = int(request.form.get("team_count", 8))
    if team_count not in ALLOWED_SIZES:
        team_count = 8

    for i in range(1, team_count + 1):
        name = request.form.get(f"team{i}", f"Team {i}")
        team = Bracket(name=name, seed=i, access_code=access_code)
        db.session.add(team)

    db.session.commit()

    teams = Bracket.query.filter(Bracket.access_code == access_code).order_by(Bracket.seed).all()
    total_rounds = int(math.log2(team_count))

    # Round 1 matches are filled with the actual teams.
    first_round_matches = team_count // 2
    for i in range(first_round_matches):
        match = Match(
            access_code=access_code,
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
                access_code=access_code,
                round=r,
                match_index=i,
                team1_id=None,
                team2_id=None
            )
            db.session.add(match)

    db.session.commit()
    return redirect(url_for('bracket_created', code=access_code))

@app.route("/reshuffle/<code>", methods=["POST"])
def reshuffle(code):
    """Randomly re-draws one round's matchups for the bracket identified by
    `code` — but ONLY a round that is completely untouched: every match in
    it must have both teams already known, and none of those matches can
    have a recorded winner yet.

    Scoped to this bracket's teams only, so shuffling one group's
    tournament never touches any other bracket's matches.
    """
    ctx = get_bracket_context(code)
    if ctx is None:
        flash('Bracket not found', 'error')
        return redirect(url_for('join_bracket'))

    target_round = ctx["reshuffle_round"]
    if target_round is None:
        # No round is currently eligible — nothing to do.
        return redirect(url_for('bracket_created', code=ctx["code"]))

    round_matches = [m for m in ctx["matches"] if m.round == target_round]
    team_ids = []
    for m in round_matches:
        team_ids.append(m.team1_id)
        team_ids.append(m.team2_id)

    random.shuffle(team_ids)

    for i, m in enumerate(round_matches):
        m.team1_id = team_ids[i * 2]
        m.team2_id = team_ids[i * 2 + 1]

    db.session.commit()
    return redirect(url_for('bracket_created', code=ctx["code"]))

@app.route("/swap_teams/<code>", methods=["POST"])
def swap_teams(code):
    """Manually swaps two teams — within the bracket identified by `code` —
    so each faces the other's current opponent. Both teams must currently
    be sitting in an undecided match (no winner yet).
    """
    ctx = get_bracket_context(code)
    if ctx is None:
        flash('Bracket not found', 'error')
        return redirect(url_for('join_bracket'))

    try:
        team_a_id = int(request.form.get("team_a"))
        team_b_id = int(request.form.get("team_b"))
    except (TypeError, ValueError):
        return redirect(url_for('bracket_created', code=ctx["code"]))

    if team_a_id == team_b_id:
        return redirect(url_for('bracket_created', code=ctx["code"]))

    pending_matches = [m for m in ctx["matches"] if m.winner_id is None]

    match_a = next((m for m in pending_matches if team_a_id in (m.team1_id, m.team2_id)), None)
    match_b = next((m for m in pending_matches if team_b_id in (m.team1_id, m.team2_id)), None)

    if not match_a or not match_b or match_a.id == match_b.id:
        # One of the teams isn't currently waiting on a match, or
        # they're already scheduled to play each other, or they don't
        # belong to this bracket at all.
        return redirect(url_for('bracket_created', code=ctx["code"]))

    if match_a.team1_id == team_a_id:
        match_a.team1_id = team_b_id
    else:
        match_a.team2_id = team_b_id

    if match_b.team1_id == team_b_id:
        match_b.team1_id = team_a_id
    else:
        match_b.team2_id = team_a_id

    db.session.commit()
    return redirect(url_for('bracket_created', code=ctx["code"]))

@app.route("/declare_winner/<int:match_id>/<int:winner_id>/<code>", methods=["POST"])
def declare_winner(match_id, winner_id, code):
    match = Match.query.get_or_404(match_id)

    if winner_id not in (match.team1_id, match.team2_id):
        return redirect(url_for('bracket_created', code=code))

    match.winner_id = winner_id
    db.session.commit()

    advance_winner(match)

    return redirect(url_for('bracket_created', code=code))

def advance_winner(match):
    """Pushes the winner of `match` into the correct slot of the next round."""
    next_round = match.round + 1
    next_match_index = match.match_index // 2

    next_match = Match.query.filter_by(
        access_code=match.access_code,
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

@app.route("/join")
def join_bracket():
    return render_template('join_bracket.html')

@app.route('/bracket/access', methods=['POST'])
def access_bracket():
    code = request.form.get('access_code', '').upper().strip()
    if not code:
        flash('Please enter a code', 'error')
        return redirect(url_for('join_bracket'))
    team = Bracket.query.filter_by(access_code=code).first()

    if not team:
        flash('Invalid code. Please try again.', 'error')
        return redirect(url_for('join_bracket'))

    return redirect(url_for('view_bracket_by_code', code=code))

@app.route('/bracket/created/<code>')
def bracket_created(code):
    ctx = get_bracket_context(code)

    if ctx is None:
        flash('Bracket not found', 'error')
        return redirect(url_for('join_bracket'))

    return render_template(
        'bracket.html',
        teams=ctx["teams"],
        rounds=ctx["rounds"],
        num_teams=ctx["num_teams"],
        allowed_sizes=ALLOWED_SIZES,
        final_match=ctx["final_match"],
        pending_teams=ctx["pending_teams"],
        reshuffle_round=ctx["reshuffle_round"],
        code=ctx["code"],
        is_creator=True,
        tournaments=get_all_tournaments()
    )

@app.route('/bracket/view/<code>')
def view_bracket_by_code(code):
    ctx = get_bracket_context(code)

    if ctx is None:
        flash('Bracket not found', 'error')
        return redirect(url_for('join_bracket'))

    tournament_name = "Tournament"

    return render_template(
        'view_bracket.html',
        code=ctx["code"],
        matches=ctx["matches"],
        teams=ctx["teams"],
        final_match=ctx["final_match"],
        tournament_name=tournament_name,
        rounds=ctx["rounds"]
        )

if __name__ == "__main__":
    app.run(debug=True)

with app.app_context():
    db.create_all()