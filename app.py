from flask import Flask, render_template
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
    team1_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

match = Match.query.get(1)
team1 = Team.query.get(match.team1_id)
team2 = Team.query.get(match.team2_id)

print(team1.name, "vs", team2.name)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/rules")
def rules():
    return render_template('rule.html')

@app.route("/bracket")
def bracket():
    teams = Team.query.all()
    matches = Match.query.order_by(Match.round, Match.match_index).all()
    return render_template('bracket.html', teams=teams, matches=matches)

@app.route("/badminton")
def badminton():
    return render_template('badminton.html')

@app.route("/football")
def football():
    return render_template('football.html')

if __name__ == "__main__":
    app.run(debug=True)