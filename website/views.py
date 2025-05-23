from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for
from flask_login import login_required, current_user
from .models import Note, BlogPost, Visitor, ContactMessage
from . import db, mail
from .forms import BlogPostForm, EditPostForm, NoteForm
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email
import json
import os
import logging
from datetime import datetime
from flask_wtf.csrf import validate_csrf
from flask_mail import Message

views = Blueprint('views', __name__)
blog = Blueprint('blog', __name__)

logging.basicConfig(level=logging.INFO)

# Contact Form
class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Send Message')

def list_files_in_directory(directory_path):
    try:
        if os.path.exists(directory_path):
            return os.listdir(directory_path)
        else:
            logging.warning(f'Directory {directory_path} does not exist.')
    except Exception as e:
        logging.error(f'Error accessing directory {directory_path}: {e}')
    return []

@views.route('/', methods=['GET', 'POST'])
def home():
    form = NoteForm()
    visitor_count = Visitor.query.count()

    flash_type = request.args.get('flash')
    flash_message = request.args.get('message')
    if flash_type and flash_message:
        flash(flash_message, category=flash_type)

    if request.method == 'POST' and current_user.is_authenticated:
        if current_user.is_guest:
            flash('Guest users cannot add notes.', category='error')
            return redirect(url_for('views.home'))
        if form.validate_on_submit():
            note = form.note.data
            if len(note) < 1:
                flash('Note is too short', category='error')
            else:
                new_note = Note(data=note, user_id=current_user.id)
                db.session.add(new_note)
                db.session.commit()
                flash('Note added', category='success')
        else:
            flash('Invalid input. Please try again.', category='error')

    return render_template("home.html", user=current_user, form=form, visitor_count=visitor_count)

@views.route('/resume')
def resume():
    return render_template('resume.html', user=current_user)

@views.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        logging.info(f"Contact form submission: Name={form.name.data}, Email={form.email.data}, Message={form.message.data}")
        try:
            contact_message = ContactMessage(
                name=form.name.data,
                email=form.email.data,
                message=form.message.data
            )
            db.session.add(contact_message)
            db.session.commit()
            logging.info(f"Stored contact message ID={contact_message.id}")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error storing contact message: {str(e)}")
        try:
            msg = Message(
                subject=f"New Contact Form Submission from {form.name.data}",
                recipients=['david.onate312@gmail.com'],
                body=f"Name: {form.name.data}\nEmail: {form.email.data}\n\nMessage:\n{form.message.data}"
            )
            mail.send(msg)
            logging.info(f"Email sent to david.onate312@gmail.com for submission from {form.email.data}")
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            flash('Message logged, but email sending failed. I’ll follow up soon!', category='warning')
            return redirect(url_for('views.home'))

        flash('Thank you for your message! I’ll get back to you soon.', category='success')
        return redirect(url_for('views.home'))
    return render_template('contact.html', form=form, user=current_user)

@views.route('/images')
@login_required
def images():
    image_folder = os.path.join(os.getcwd(), 'static', 'images')
    image_list = list_files_in_directory(image_folder)
    return render_template("images.html", images=image_list, user=current_user)

@views.route('/delete-note/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    if current_user.is_guest:
        logging.warning(f'Guest user {current_user.id} attempted to delete note {note_id}')
        return jsonify({'success': False, 'message': 'Guest users cannot delete notes'}), 403

    csrf_token = request.headers.get('X-CSRF-Token')
    try:
        validate_csrf(csrf_token)
    except Exception as e:
        logging.error(f'CSRF validation failed for note {note_id}: {str(e)}')
        return jsonify({'success': False, 'message': 'Invalid CSRF token'}), 403

    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        logging.warning(f'Unauthorized attempt to delete note {note_id} by user {current_user.id}')
        return jsonify({'success': False, 'message': 'You are not authorized to delete this note'}), 403

    try:
        db.session.delete(note)
        db.session.commit()
        logging.info(f'Note {note_id} deleted by user {current_user.id}')
        return jsonify({'success': True, 'message': 'Note deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error deleting note {note_id}: {str(e)}')
        return jsonify({'success': False, 'message': 'An error occurred while deleting the note'}), 500

@views.route('/certs')
def certs():
    certs_folder = os.path.join(os.getcwd(), 'static', 'images')
    certs_list = list_files_in_directory(certs_folder)
    return render_template('certs.html', images=certs_list, user=None)

@views.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('You are not authorized to access the admin dashboard.', category='error')
        return redirect(url_for('views.home'))
    posts = BlogPost.query.all()
    messages = ContactMessage.query.all()
    visitor_count = Visitor.query.count()

    # Log and handle posts with missing dates
    for post in posts:
        if post.date is None:
            logging.warning(f"Post with ID {post.id} has no date.")
            post.date = datetime.utcnow()  # Set a default date if necessary
    return render_template('admin_dashboard.html', user=current_user, posts=posts, messages=messages, visitor_count=visitor_count)

@blog.route('/post', methods=['GET', 'POST'])
@login_required
def create_post():
    if not current_user.is_admin:
        flash('You are not authorized to create posts.', category='error')
        return redirect(url_for('views.home'))
    form = BlogPostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            content=form.content.data,
            author=current_user.id
        )
        db.session.add(new_post)
        db.session.commit()
        flash('Blog post created successfully!', category='success')
        return redirect(url_for('blog.view_blogposts'))
    return render_template('create_post.html', form=form, user=current_user)

@blog.route('/view_posts')
def view_blogposts():
    posts = BlogPost.query.all()

    for post in posts:
        if post.date is None:
            logging.warning(f"Post with ID {post.id} has no date.")
            post.date = datetime.utcnow()  # Set a default date if necessary
    return render_template('view_blogposts.html', posts=posts, user=current_user)

@blog.route('/delete_post/<int:post_id>', methods=['DELETE'])
@login_required
def delete_post(post_id):
    if not current_user.is_admin:
        flash('You are not authorized to delete posts.', category='error')
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    csrf_token = request.headers.get('X-CSRF-Token')
    try:
        validate_csrf(csrf_token)
    except Exception as e:
        logging.error(f'CSRF validation failed for post {post_id}: {str(e)}')
        return jsonify({'success': False, 'message': 'Invalid CSRF token'}), 403
    
    post = BlogPost.query.get_or_404(post_id)
    try:
        db.session.delete(post)
        db.session.commit()
        logging.info(f'Post {post_id} deleted by user {current_user.id}')
        return jsonify({'success': True, 'message': 'Post deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error deleting post {post_id}: {str(e)}')
        return jsonify({'success': False, 'message': 'An error occurred while deleting the post'}), 500

@blog.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    if not current_user.is_admin:
        flash('You are not authorized to edit posts.', category='error')
        return redirect(url_for('blog.view_blogposts'))
    post = BlogPost.query.get_or_404(post_id)
    form = EditPostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash('Post updated successfully!', category='success')
        return redirect(url_for('blog.view_blogposts'))
    return render_template('edit_post.html', form=form, post=post, user=current_user)

@views.route('/visitor-counter')
def visitor_counter():
    return render_template('visitor_counter.html', user=current_user)