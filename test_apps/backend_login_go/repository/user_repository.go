package repository

import (
	"backend_login_go/model"
	"database/sql"
)

type UserRepository struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

func (u *UserRepository) GetUser(username string) (*model.User, error) {
	var user model.User
	err := u.db.QueryRow("SELECT id, username, status, password FROM users WHERE username = $1", username).Scan(&user.ID, &user.Username, &user.Status, &user.Password)
	if err != nil {
		return nil, err
	}
	return &user, nil
}