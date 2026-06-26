from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///Bracket.db'
db = SQLAlchemy(app)

class Bracket(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    seed = db.Column(db.Integer, nullable=False)

class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer, nullable=False)
    match_index= db.Column(db.Integer, nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    team2_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    team1 = db.relationship('Bracket', foreign_keys=[team1_id])
    team2 = db.relationship('Bracket', foreign_keys=[team2_id])
    winner = db.relationship('Bracket', foreign_keys=[winner_id])

@app.route("/")
def index():
    print('Index')
    return render_template('index.html')

@app.route("/bracket")
def bracket():
    teams = Bracket.query.all()
    matches = Match.query.order_by(Match.round, Match.match_index).all()
    return render_template('bracket.html', teams=teams, matches=matches)

@app.route("/setup", methods=["POST"])
def setup():
    Match.query.delete()
    Bracket.query.delete()

    for i in range(1, 17):
        name = request.form.get(f"team{i}", f"Team {i}")
        team = Bracket(name=name, seed=i)
        db.session.add(team)
    
    db.session.commit()

    teams = Bracket.query.order_by(Bracket.seed).all()

    for i in range(8):
        match = Match(
            round=1,
            match_index=i,
            team1_id=teams[i * 2].id,
            team2_id=teams[i * 2 + 1].id
        )
        db.session.add(match)
    
    for round_num, count in [(2,4), (3,2), (4,1)]:
            for i in range(count):
                match = Match(
                    round=round_num,
                    match_index=i,
                    team1_id=None,
                    team2_id=None
                )
                db.session.add(match)

    db.session.commit()
    return redirect(url_for('bracket'))

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
    with app.app_context():
        db.create_all()
    app.run(debug=True)