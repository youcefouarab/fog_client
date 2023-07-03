'''
    This module contains metaclasses.

    Classes:
    --------
    SingletonMeta: Thread-safe implementation of Singleton design pattern.
'''


from threading import Lock


class SingletonMeta(type):
    '''
        Thread-safe implementation of Singleton design pattern.
    '''

    _instances = {}
    # to synchronize threads during first access to Singleton
    _lock: Lock = Lock()

    # possible changes to value of `__init__` argument do not affect returned
    # instance.
    def __call__(cls, *args, **kwargs):
        # Now, imagine that the program has just been launched. Since there's
        # no Singleton instance yet, multiple threads can simultaneously pass
        # the previous conditional and reach this point almost at the same
        # time. The first of them will acquire lock and will proceed further,
        # while the rest will wait here.
        with cls._lock:
            # The first thread to acquire the lock, reaches this conditional,
            # goes inside and creates the Singleton instance. Once it leaves
            # the lock block, a thread that might have been waiting for lock
            # release may enter this section. But since the Singleton field is
            # already initialized, the thread won't create a new object.
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]
