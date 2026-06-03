#pragma once
#include <mutex>
#include <condition_variable>
#include <queue>
#include <functional>
#include <chrono>
template<typename Element>
class SynchronizedQueue
{
private:
	std::mutex lock;
	std::condition_variable pop_cond, push_cond;
	size_t maxSize;
	std::queue<Element> queue;
	bool has_space() {
		return queue.size() < maxSize;
	}
	bool has_elements() {
		return !queue.empty();
	}
public:	
	bool is_full() {
		return queue.size() >= maxSize;
	};
	bool is_empty() {
		return queue.empty();
	};
	bool wait_for_not_empty(std::chrono::milliseconds timeout = std::chrono::milliseconds(1000000)) {
		std::unique_lock<std::mutex> m_lock(lock);
		if (pop_cond.wait_for(m_lock, timeout, [this] {return !is_empty(); }))
			return true;
		return false;
	}
	bool push(Element &el,std::chrono::milliseconds timeout= std::chrono::milliseconds(1000000)) {
		std::unique_lock<std::mutex> m_lock(lock);
		if (push_cond.wait_for(m_lock, timeout,[this] {return !is_full(); })) {
			queue.push(el);
			pop_cond.notify_one();
			return true;
		}
		return false;
			
	};
	bool pop(Element &el, std::chrono::milliseconds timeout = std::chrono::milliseconds(1000000)) {
		std::unique_lock<std::mutex> m_lock(lock);
		if (pop_cond.wait_for(m_lock, timeout, [this] {return !is_empty(); })) {
			el = queue.front();
			queue.pop();
			push_cond.notify_one();
			return true;
		}
		return false;
	};
	void clear() {
		std::lock_guard<std::mutex> m_lock(lock);
		std::queue<Element> empty;
		std::swap(queue, empty);
		push_cond.notify_one();
	}
	size_t size() {
		return queue.size();
	}
	SynchronizedQueue(size_t maxSize) :maxSize(maxSize) {};
	~SynchronizedQueue() {};
};
