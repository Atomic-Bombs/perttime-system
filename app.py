from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'perttime-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mendan.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "セッションが切れました。再度ログインしてください。"
login_manager.login_message_category = "error"

app.permanent_session_lifetime = timedelta(minutes=30)

# ユーザーテーブル
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 生徒テーブル (★変更: grade, school を追加)
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(50), nullable=False)   # 追加: 学年
    school = db.Column(db.String(100), nullable=False) # 追加: 学校名
    records = db.relationship('Record', backref='student', lazy=True)

# 面談記録テーブル
class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    instructor = db.Column(db.String(100))
    deliverables = db.Column(db.Text)
    assignment = db.Column(db.Text)
    memo = db.Column(db.Text)
    next_meeting_date = db.Column(db.String(20))
    next_instructor = db.Column(db.String(100))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ログイン
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        code = request.form['code']
        password = request.form['password']
        user = User.query.filter_by(code=code).first()
        if user and user.check_password(password):
            login_user(user)
            session.permanent = True
            return redirect(url_for('index'))
        flash('ユーザー名またはパスワードが違います', 'error')
    return render_template('login.html')

# ログアウト
@app.route('/logout')
def logout():
    logout_user()
    reason = request.args.get('reason')
    if reason == 'timeout':
        flash('一定時間操作がなかったため、セッションが切れました。再度ログインしてください。', 'error')
    return redirect(url_for('login'))

# トップページ（生徒一覧 ＋ ★検索・絞り込み機能追加）
@app.route('/')
@login_required
def index():
    # URLパラメータから検索条件を取得
    search_name = request.args.get('search_name', '')
    grade = request.args.get('grade', '')

    # クエリのベースを作成
    query = Student.query

    # 名前で検索（入力があれば部分一致で絞り込み）
    if search_name:
        query = query.filter(Student.name.contains(search_name))
    
    # 学年で絞り込み（選択されていれば完全一致で絞り込み）
    if grade:
        query = query.filter(Student.grade == grade)

    # 最終的な結果を取得
    students = query.all()
    
    return render_template('index.html', students=students)

# 生徒追加 (★変更: GET処理追加 ＆ 学年・学校名の保存処理追加)
@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'GET':
        # 入力画面を表示
        return render_template('add_student.html')

    if request.method == 'POST':
        # フォームからデータを受け取り保存
        name = request.form['name']
        grade = request.form['grade']
        school = request.form['school']
        
        student = Student(name=name, grade=grade, school=school)
        db.session.add(student)
        db.session.commit()
        
        flash('生徒を新規追加しました！')
        return redirect(url_for('index'))

# 面談記録一覧
@app.route('/student/<int:student_id>')
@login_required
def student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    records = Record.query.filter_by(student_id=student_id).order_by(Record.date.desc()).all()
    return render_template('detail.html', student=student, records=records, error=None, form_data={})

# 面談記録追加
@app.route('/add_record/<int:student_id>', methods=['GET', 'POST'])
@login_required
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
    return render_template('add_record.html', student=student, error=error, form_data=form_data)

# 面談記録の編集
@app.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@login_required
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
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    Record.query.filter_by(student_id=student_id).delete()
    db.session.delete(student)
    db.session.commit()
    flash('生徒を削除しました', 'success')
    return redirect(url_for('index'))

# 面談記録削除
@app.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = Record.query.get_or_404(record_id)
    student_id = record.student_id
    db.session.delete(record)
    db.session.commit()
    flash('記録を削除しました', 'success')
    return redirect(url_for('student_detail', student_id=student_id))

# 管理者画面
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('管理者のみアクセスできます', 'error')
        return redirect(url_for('index'))
    users = User.query.all()
    return render_template('admin.html', users=users)

# アカウント追加
@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    code = request.form['code']
    password = request.form['password']
    is_admin = 'is_admin' in request.form
    if User.query.filter_by(code=code).first():
        flash('そのバイトコードはすでに登録されています', 'error')
        return redirect(url_for('admin'))
    user = User(code=code, is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash('アカウントを追加しました', 'success')
    return redirect(url_for('admin'))

# アカウント削除
@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('自分自身は削除できません', 'error')
        return redirect(url_for('admin'))
    db.session.delete(user)
    db.session.commit()
    flash('アカウントを削除しました', 'success')
    return redirect(url_for('admin'))

# 権限変更
@app.route('/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('自分自身の権限は変更できません', 'error')
        return redirect(url_for('admin'))
    user.is_admin = not user.is_admin
    db.session.commit()
    flash('権限を変更しました', 'success')
    return redirect(url_for('admin'))

# パスワード変更
@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    error = None
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if not current_user.check_password(current_password):
            error = '現在のパスワードが違います'
        elif new_password != confirm_password:
            error = '新しいパスワードが一致しません'
        elif current_user.check_password(new_password):
            error = '現在と同じパスワードは使用できません'
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('パスワードを変更しました', 'success')
            return redirect(url_for('index'))
    return render_template('change_password.html', error=error)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)