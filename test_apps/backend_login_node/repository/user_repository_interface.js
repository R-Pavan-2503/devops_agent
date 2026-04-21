class UserRepositoryInterface {
    async getUser(username) {
        throw new Error('Method not implemented');
    }

    async createUser(username, password) {
        throw new Error('Method not implemented');
    }
}

module.exports = UserRepositoryInterface;