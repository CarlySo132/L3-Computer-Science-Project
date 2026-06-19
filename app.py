from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/rules")
def rules():
    return render_template('rule.html')

@app.route("/bracket")
def bracket():
    return render_template('bracket.html')

if __name__ == "__main__":
    app.run(debug=True)