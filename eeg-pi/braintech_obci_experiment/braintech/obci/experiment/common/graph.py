# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.


class DirectedGraph:
    def __init__(self):
        self._edges = []
        self._neighbours = {}

    def copy(self):
        gr = DirectedGraph()
        copied = {}
        for v1, v2 in self._edges:
            for v in (v1, v2):
                if v._model not in copied:
                    copied[v._model] = v.copy(gr)
            cv1 = copied[v1._model]
            cv2 = copied[v2._model]
            gr.add_edge(cv1, cv2)
        for v in self._neighbours:
            if self._neighbours[v] == [] and not v.in_edges():
                gr.add_vertex(v.copy(gr))
        return gr

    @property
    def vertices(self):
        return self._neighbours.keys()

    def add_vertex(self, vertex):
        if vertex not in self._neighbours:
            self._neighbours[vertex] = []

    def add_edge(self, v_a, v_z):
        for v in [v_a, v_z]:
            if v not in self._neighbours:
                self._neighbours[v] = []
        if v_z not in self._neighbours[v_a]:
            self._neighbours[v_a].append(v_z)
            self._edges.append((v_a, v_z))

    def remove_edge(self, edge):
        v_a, v_z = edge
        if (v_a, v_z) in self._edges:
            self._edges.remove((v_a, v_z))
            self._neighbours[v_a].remove(v_z)
        else:
            raise Exception('edge not in graph')

    def remove_vertex(self, vertex):
        if vertex not in self._neighbours:
            raise Exception('vertex not in graph')
        ins = vertex.in_edges()
        outs = vertex.out_edges()
        for e in ins + outs:
            self.remove_edge(e)
        del self._neighbours[vertex]

    def topo_sort(self):
        gr = self.copy()
        result = []
        len_res = 0
        cycle = False
        while not len_res == len(self.vertices):
            sinks = [v for v in gr.vertices
                     if not v.out_edges()]
            if not sinks:
                cycle = True
                break
            result.append(sinks)
            len_res += len(sinks)
            for s in sinks:
                for ine in s.in_edges():
                    gr.remove_edge(ine)
            for i in range(len(sinks)):
                gr.remove_vertex(sinks[i])
        has_unconsumed_edges = bool(gr._edges)
        if has_unconsumed_edges:
            cycle = True
        return not cycle, result


class Vertex:
    def __init__(self, graph, model, id_method=None):
        self._model = model
        self._graph = graph

    def __str__(self):
        return self._model.__str__()

    def __repr__(self):
        return self._model.__str__()

    def copy(self, new_graph):
        return Vertex(new_graph, self._model)

    def neighbours(self):
        return self._graph._neighbours[self]

    def out_edges(self):
        return [(self, n) for n in self.neighbours()]

    def in_edges(self):
        return [(ver, self) for ver in self._graph.vertices
                if (ver, self) in self._graph._edges]
