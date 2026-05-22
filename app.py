from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'perttime-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mendan.db'
db = SQLAlchemy(app)

# 生徒テーブル
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    records = db.relationship('Record', backref='student', lazy=True)

# 面談記録テーブル
class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    instructor = db.Column(db.String(100))
    deliverables = db.Column(db.Text)        # 追加
    assignment = db.Column(db.Text)          # 追加
    memo = db.Column(db.Text)
    next_meeting_date = db.Column(db.String(20))
    next_instructor = db.Column(db.String(100))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

# トップページ（生徒一覧）
@app.route('/')
def index():
    students = Student.query.all()
    return render_template('index.html', students=students)

# 生徒追加
@app.route('/add_student', methods=['POST'])
def add_student():
    name = request.form['name']
    student = Student(name=name)
    db.session.add(student)
    db.session.commit()
    flash('生徒を保存しました！')
    return redirect(url_for('index'))

# 面談記録一覧
@app.route('/student/<int:student_id>')
def student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template('detail.html', student=student, error=None, form_data={})

# 面談記録追加
@app.route('/add_record/<int:student_id>', methods=['GET', 'POST'])
def add_record(student_id):
    student = Student.query.get_or_404(student_id)
    error = None
    form_data = {}
    if request.method == 'POST':
        form_data = request.form
        date_val = request.form['date']
        next_meeting_date = request.form['next_meeting_date']
        if next_meeting_date and next_meeting_date <= date_val:
            error = '次回面談日は面談日より後の日付にしてください'
        else:
            record = Record(
                date=date_val,
                instructor=request.form['instructor'],
                deliverables=request.form['deliverables'],
                assignment=request.form['assignment'],
                memo=request.form['memo'],
                next_meeting_date=next_meeting_date,
                next_instructor=request.form['next_instructor'],
                student_id=student_id
            )
            db.session.add(record)
            db.session.commit()
            flash('記録を保存しました！', 'success')
            return redirect(url_for('student_detail', student_id=student_id))
    return render_template('detail.html', student=student, error=error, form_data=form_data)

# 面談記録の編集
@app.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
def edit_record(record_id):
    record = Record.query.get_or_404(record_id)
    error = None
    success = None
    if request.method == 'POST':
        date = request.form['date']
        next_meeting_date = request.form['next_meeting_date']
        if next_meeting_date and next_meeting_date <= date:
            error = '次回面談日は面談日より後の日付にしてください'
        else:
            record.date = date
            record.instructor = request.form['instructor']
            record.deliverables = request.form['deliverables']
            record.assignment = request.form['assignment']
            record.memo = request.form['memo']
            record.next_meeting_date = next_meeting_date
            record.next_instructor = request.form['next_instructor']
            db.session.commit()
            flash('保存が完了しました！')
            return redirect(url_for('student_detail', student_id=record.student_id))
    return render_template('edit.html', record=record, error=error, success=success)

# 生徒削除
@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    Record.query.filter_by(student_id=student_id).delete()
    db.session.delete(student)
    db.session.commit()
    flash('生徒を削除しました', 'success')
    return redirect(url_for('index'))

# 面談記録削除
@app.route('/delete_record/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    record = Record.query.get_or_404(record_id)
    student_id = record.student_id
    db.session.delete(record)
    db.session.commit()
    flash('記録を削除しました', 'success')
    return redirect(url_for('student_detail', student_id=student_id))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)