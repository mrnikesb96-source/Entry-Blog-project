from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
# from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, nulls_last, ForeignKey, Boolean, Date
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm,LoginForm,CommentForm

app = Flask(__name__)
app.config["SECRET_KEY"] = "8BYkEfBA6O6donzWlSihBXox7C0sKR6b"
ckeditor = CKEditor(app)
Bootstrap5(app)

class Base(DeclarativeBase):
    pass

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///posts.db"
db = SQLAlchemy(model_class=Base)
db.init_app(app)
migrate = Migrate(app,db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    title: Mapped[str] = mapped_column(String(100),unique=True,nullable=False)
    subtitle: Mapped[str] = mapped_column(String(100),nullable=False)
    date: Mapped[str] = mapped_column(String(100),nullable=False)
    body: Mapped[str] = mapped_column(Text,nullable=False)
    author: Mapped[str] = mapped_column(String(100),nullable=False)
    img_url: Mapped[str] = mapped_column(String(250),nullable=False)
    # add a foreign key to tie the two tables together
    account_id : Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id",name="fk_blogpost_account_id"),
        nullable=True
    )
    # ties blogpost back to a given user
    author_rel: Mapped["User"] = relationship(back_populates="blogs")
    comments: Mapped[list["Comment"]] = relationship(back_populates="blog")


class User(db.Model,UserMixin):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    username: Mapped[str] = mapped_column(String(100),nullable=False)
    email: Mapped[str] = mapped_column(String(100),nullable=False,unique=True)
    password: Mapped[str] = mapped_column(String(100),nullable=False)
    # allows getting user's blogposts without needing to query for them
    blogs: Mapped[list["BlogPost"]] = relationship(back_populates="author_rel")
    comments: Mapped[list["Comment"]] = relationship(back_populates="comment_author")

    def __init__(self,username:str,email:str,password:str):
        self.username = username
        self.email = email
        self.password = password

class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    text: Mapped[str] = mapped_column(Text,nullable=False)
    date: Mapped[date] = mapped_column(Date,default=date.today, nullable=False)
    blog_post_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blog_posts.id",name="fk_blog_post_comment_id"),
        nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id",name="fk_user_comment_id"),
        nullable=False
    )
    comment_author: Mapped["User"] = relationship(back_populates="comments")
    blog: Mapped["BlogPost"] = relationship(back_populates="comments")


# Wrapper Function
def check_admin(func):
    @wraps(func)
    def wrapper(*args,**kwargs):
        if not current_user.is_authenticated and current_user.id != 1:
            flash("Easy Now, Admins only!","warning")
            return redirect(url_for("get_all_posts"))
        return func(*args,**kwargs)
    return wrapper


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User,int(user_id))

# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register',methods=["GET","POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        chosen_username = form.username.data
        user_email = form.email.data
        user_password = form.password.data
        existing_user = db.session.execute(db.select(User).where(getattr(User,"email") == user_email)).scalar()
        if not existing_user:
            hashed_pass = generate_password_hash(user_password,"pbkdf2:sha256",salt_length=8)
            try:
                new_user = User(
                    username=chosen_username,
                    email = user_email,
                    password = hashed_pass
                )
                db.session.add(new_user)
                db.session.commit()
                flash(f"{chosen_username.title()} has successfully been added to the Blog, welcome!","success")
            except SQLAlchemyError:
                db.session.rollback()
                flash("Sorry an error occurred during account creation, try again later.","danger")
            return redirect(url_for("login"))
        else:
            flash("Sorry this email is already registered","danger")
    return render_template("register.html",form=form)


# TODO: Retrieve a user from the database based on their email.
@app.route('/login',methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        submitted_email = form.email.data
        submitted_password = form.password.data
        user = db.session.execute(db.select(User).where(User.email==submitted_email)).scalar()
        if user:
            valid = check_password_hash(user.password,submitted_password)
            if valid:
                login_user(user)
                flash("Successful login","success")
                return redirect(url_for("get_all_posts"))
            else:
                flash("Password Incorrect","danger")
                return render_template("login.html",form=form)
        else:
            flash("Email not found","danger")
            return render_template("login.html",form=form)
    return render_template("login.html",form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Successful Logged Out","success")
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>",methods=["GET","POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_section = [comment for comment in requested_post.comments]
    form = CommentForm()
    # form only displays if logged in so no need to check
    if form.validate_on_submit():
        try:
            new_comment = Comment(
                text=form.body.data,
                blog_post_id=requested_post.id,
                account_id=current_user.id
            )
            db.session.add(new_comment)
            db.session.commit()
            flash("Comment added ✔️","success")
        except SQLAlchemyError:
            db.session.rollback()
            flash("Sorry an error occured while proccessing your comment, try again later.","danger")
        return redirect(url_for("show_post",post_id=post_id))
    return render_template(
        "post.html",
        post=requested_post,
        comments=comment_section,
        form=form,
    )


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@login_required
@check_admin
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@login_required
@check_admin
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@login_required
@check_admin
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=True, port=5002)