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
    """Generate a random 6-chracter access code like ABC123"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/bracket")
def bracket():
    return render_template(
        'bracket.html',
        teams=[],
        rounds=[],
        num_teams=0,
        allowed_sizes=ALLOWED_SIZES,
        final_match=None
    )

@app.route("/setup", methods=["POST"])
def setup():
    access_code = generate_access_code()

    team_count = int(request.form.get("team_count", 8))
    if team_count not in ALLOWED_SIZES:
        team_count = 8

    Match.query.delete()
    Bracket.query.delete()

    for i in range(1, team_count + 1):
        name = request.form.get(f"team{i}", f"Team {i}")
        team = Bracket(name=name, seed=i, access_code=access_code)
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
    return redirect(url_for('bracket_created', code=access_code))

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
        return  # match.round was the final, nothing further to advance to

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

@app.route("/bracket/join")
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


@app.route('/bracket/view/<code>')
def view_bracket_by_code(code):
    code = code.upper()

    teams = Bracket.query.filter_by(access_code=code).all()

    if not teams:
        flash('Bracket not found', 'error')
        return redirect(url_for('join_bracket'))

    team_ids = [t.id for t in teams]
    matches = Match.query.filter(
        (Match.team1_id.in_(team_ids)) | (Match.team2_id.in_(team_ids))
    ).all()

    final_match = None
    for match in matches :
        if match.round == 3 and match.winner_id:
            final_match = match
            break

    tournament_name = "Tournament"

    round_dict = {}
    for match in matches:
        if match.round not in round_dict:
            round_dict[match.round] = []
        round_dict[match.round].append(match)

    rounds = [
        {'number': r, 'matches': round_dict[r]}
        for r in sorted(round_dict.keys())
    ]
    return render_template('view_bracket.html',
                           code=code,
                           matches=matches,
                           teams=teams,
                           final_match=final_match,
                           tournament_name=tournament_name,
                           rounds=rounds)

@app.route('/bracket/created/<code>')
def bracket_created(code):
    code = code.upper()

    teams = Bracket.query.filter_by(access_code=code).all()

    if not teams:
        flash('Bracket not found', 'error')
        return redirect(url_for('join_bracket'))

    team_ids = [t.id for t in teams]
    matches = Match.query.filter(
        (Match.team1_id.in_(team_ids)) | (Match.team2_id.in_(team_ids))
    ).all()

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

    return render_template(
        'bracket.html',
        teams=teams,
        rounds=rounds,
        num_teams=num_teams,
        allowed_sizes=ALLOWED_SIZES,
        final_match=final_match, 
        code=code,
        is_creator=True
        )

if __name__ == "__main__":
    app.run(debug=True)

with app.app_context():
    db.create_all()