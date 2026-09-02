from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_migrate import Migrate

app = Flask(__name__)
app.secret_key = 'perttime-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mendan.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    if 'user_id' in session:
        flash("セッションの有効期限が切れました。再度ログインしてください。", "error")
    return redirect(url_for('login'))

app.permanent_session_lifetime = timedelta(minutes=30)

# 学年の色を計算するカスタムフィルター（高1=赤、高2=黄、高3=青）
@app.template_filter('grade_color')
def grade_color_filter(grade_str):
    now = datetime.now()
    year = now.year
    if now.month < 4:  # 1月〜3月は前年度として扱う
        year -= 1
    
    grade_num = 1
    if "2" in grade_str:
        grade_num = 2
    elif "3" in grade_str:
        grade_num = 3
        
    entrance_year = year - (grade_num - 1)
    color_index = entrance_year % 3
    
    # 2026年度基準の正しい割り当て：
    # 2026年入学（高1）: 2026 % 3 = 1 -> 赤
    # 2025年入学（高2）: 2025 % 3 = 0 -> 黄
    # 2024年入学（高3）: 2024 % 3 = 2 -> 青
    if color_index == 1:
        return "bg-red-50 border-red-200 text-red-700"          # 赤系
    elif color_index == 0:
        return "bg-yellow-50 border-yellow-200 text-yellow-700"  # 黄系
    else:
        return "bg-blue-50 border-blue-200 text-blue-700"        # 青系

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

# 生徒テーブル
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    school = db.Column(db.String(100), nullable=False)
    records = db.relationship('Record', backref='student', lazy=True)

# 月別受講状況テーブル
class MonthlyProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    monthly_goal = db.Column(db.Float)
    current_progress = db.Column(db.Float)

    student = db.relationship(
        'Student',
        backref=db.backref('monthly_progresses', lazy=True)
    )

    __table_args__ = (
        db.UniqueConstraint('student_id', 'month', name='unique_student_month'),
    )

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
            session.permanent = False
            return redirect(url_for('index'))
        flash('ユーザー名またはパスワードが違います', 'error')
    return render_template('login.html')

# ログアウト
@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    reason = request.args.get('reason')
    if reason == 'timeout':
        flash('一定時間操作がなかったため、セッションが切れました。再度ログインしてください。', 'error')
    return redirect(url_for('login'))

# トップページ（生徒一覧）
@app.route('/')
@login_required
def index():
    search_name = request.args.get('search_name', '')
    grade = request.args.get('grade', '')
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 本日の面談予定
    today_records = Record.query.filter(
        Record.next_instructor == current_user.code,
        Record.next_meeting_date == today_str
    ).order_by(Record.next_meeting_date.asc()).all()

    # 明日以降の面談予定
    upcoming_records = Record.query.filter(
        Record.next_instructor == current_user.code,
        Record.next_meeting_date > today_str
    ).order_by(Record.next_meeting_date.asc()).all()

    query = Student.query

    if search_name:
        query = query.filter(Student.name.contains(search_name))

    if grade:
        query = query.filter(Student.grade == grade)

    students = query.all()

    return render_template(
        'index.html',
        students=students,
        today_records=today_records,
        upcoming_records=upcoming_records
    )

# 生徒追加
@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'GET':
        return render_template('add_student.html')

    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']
        school = request.form['school']
        
        student = Student(name=name, grade=grade, school=school)
        db.session.add(student)
        db.session.commit()
        
        flash('生徒を新規追加しました！')
        return redirect(url_for('index'))

# 生徒情報の編集
@app.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        student.name = request.form['name']
        student.grade = request.form['grade']
        student.school = request.form['school']
        db.session.commit()
        flash('生徒情報を更新しました！', 'success')
        return redirect(url_for('student_detail', student_id=student.id))
    return render_template('edit_student.html', student=student)

# 面談記録一覧
@app.route('/student/<int:student_id>')
@login_required
def student_detail(student_id):
    student = Student.query.get_or_404(student_id)

    current_month_date = datetime.now().replace(day=1)
    current_month = current_month_date.strftime('%Y-%m')

    selected_month = request.args.get('month', current_month)

    # 不正な月指定があった場合は今月に戻す
    try:
        selected_month_date = datetime.strptime(selected_month, '%Y-%m')
    except ValueError:
        selected_month_date = current_month_date
        selected_month = current_month

    # 前月
    prev_month_date = selected_month_date - timedelta(days=1)
    prev_month_date = prev_month_date.replace(day=1)
    prev_month = prev_month_date.strftime('%Y-%m')

    # 翌月
    next_month_date = selected_month_date.replace(day=28) + timedelta(days=4)
    next_month_date = next_month_date.replace(day=1)
    next_month = next_month_date.strftime('%Y-%m')

    # 選択中の月の受講状況
    monthly_progress = MonthlyProgress.query.filter_by(
        student_id=student.id,
        month=selected_month
    ).first()

    # 登録済みの月別受講状況
    monthly_progresses = MonthlyProgress.query.filter_by(
        student_id=student.id
    ).order_by(
        MonthlyProgress.month.desc()
    ).all()

    records = Record.query.filter_by(
        student_id=student.id
    ).order_by(
        Record.date.desc()
    ).all()

    return render_template(
        'detail.html',
        student=student,
        records=records,
        current_month=current_month,
        selected_month=selected_month,
        prev_month=prev_month,
        next_month=next_month,
        monthly_progress=monthly_progress,
        monthly_progresses=monthly_progresses
    )

# 面談記録追加
@app.route('/add_record/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_record(student_id):
    student = Student.query.get_or_404(student_id)
    error = None
    form_data = {}
    users = User.query.all()

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
                deliverables=request.form['deliverables'].strip(),
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
    return render_template('add_record.html', student=student, error=error, form_data=form_data, users=users)

# 月別受講状況の編集
@app.route('/edit_progress/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit_progress(student_id):
    student = Student.query.get_or_404(student_id)

    # URLから対象月を取得
    month = request.args.get('month')

    # monthが指定されていなければ現在の月
    if not month:
        month = datetime.now().strftime('%Y-%m')

    # 対象月のデータを取得
    progress = MonthlyProgress.query.filter_by(
        student_id=student_id,
        month=month
    ).first()

    # データがなければ新規作成
    if not progress:
        progress = MonthlyProgress(
            student_id=student_id,
            month=month
        )

    if request.method == 'POST':
        monthly_goal = request.form.get('monthly_goal')
        current_progress = request.form.get('current_progress')

        progress.monthly_goal = float(monthly_goal) if monthly_goal else None
        progress.current_progress = float(current_progress) if current_progress else None

        # 新規データならDBに追加
        if progress.id is None:
            db.session.add(progress)

        db.session.commit()

        flash('受講状況を更新しました！', 'success')
        return redirect(url_for(
            'student_detail',
            student_id=student_id,
            month=month
        ))

    return render_template(
        'edit_progress.html',
        student=student,
        progress=progress,
        month=month
    )

# 面談記録の編集
@app.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    record = Record.query.get_or_404(record_id)
    error = None
    success = None

    # 担当者一覧を取得
    users = User.query.all()

    if request.method == 'POST':
        date = request.form['date']
        next_meeting_date = request.form['next_meeting_date']

        if next_meeting_date and next_meeting_date <= date:
            error = '次回面談日は面談日より後の日付にしてください'
        else:
            record.date = date
            record.instructor = request.form['instructor']
            record.deliverables = request.form['deliverables'].strip()
            record.assignment = request.form['assignment'].strip()
            record.memo = request.form['memo'].strip()
            record.next_meeting_date = next_meeting_date
            record.next_instructor = request.form['next_instructor']

            db.session.commit()

            flash('保存が完了しました！')
            return redirect(
                url_for(
                    'student_detail',
                    student_id=record.student_id
                )
            )

    return render_template(
        'edit.html',
        record=record,
        error=error,
        success=success,
        users=users
    )

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

# 年次更新（一括進級処理）
@app.route('/advance_years', methods=['POST'])
@login_required
def advance_years():
    if not current_user.is_admin:
        flash('管理者のみ実行できます', 'error')
        return redirect(url_for('index'))
    
    students = Student.query.all()
    for student in students:
        if student.grade == '高校3年生':
            # 高校3年生の場合、紐づく面談記録をすべて削除
            Record.query.filter_by(student_id=student.id).delete()
            # 生徒データ自体も削除
            db.session.delete(student)
        elif student.grade == '高校2年生':
            student.grade = '高校3年生'
        elif student.grade == '高校1年生':
            student.grade = '高校2年生'
            
    db.session.commit()
    flash('新年度への進級処理が完了しました！高校3年生のデータは自動的に削除されました。', 'success')
    return redirect(url_for('admin'))

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